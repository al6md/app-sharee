package iq.sharecoc.app.data.network

import android.util.Base64
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import iq.sharecoc.app.config.AppConfig
import iq.sharecoc.app.data.models.CloudAdminStore
import iq.sharecoc.app.data.models.DriveItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class GoogleDriveApiClient private constructor() {

    companion object {
        private const val TAG = "ShareCocApiClient"
        private const val LEGACY_ROOT_ID = "1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB"

        @Volatile
        private var instance: GoogleDriveApiClient? = null

        fun getInstance(): GoogleDriveApiClient {
            return instance ?: synchronized(this) {
                instance ?: GoogleDriveApiClient().also { instance = it }
            }
        }
    }

    private val gson = Gson()
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(AppConfig.CONNECT_TIMEOUT_SEC, TimeUnit.SECONDS)
        .readTimeout(AppConfig.READ_TIMEOUT_SEC, TimeUnit.SECONDS)
        .writeTimeout(AppConfig.READ_TIMEOUT_SEC, TimeUnit.SECONDS)
        .build()

    private fun normalizeFolderId(id: String): String {
        return if (id.isBlank() || id == LEGACY_ROOT_ID) "root" else id
    }

    private fun decodeFolderPath(folderId: String): String {
        val norm = normalizeFolderId(folderId)
        if (norm == "root") return ""
        if (norm.startsWith("loc_")) {
            return try {
                val encoded = norm.removePrefix("loc_")
                val bytes = Base64.decode(encoded, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
                String(bytes, Charsets.UTF_8).trim('/')
            } catch (_: Exception) {
                ""
            }
        }
        return ""
    }

    private fun postJsonAction(payload: JsonObject): JsonObject {
        val req = Request.Builder()
            .url("${AppConfig.SERVER_BASE_URL}/api/drive/files")
            .addHeader("x-admin-role", "admin")
            .post(payload.toString().toRequestBody(jsonMediaType))
            .build()

        client.newCall(req).execute().use { response ->
            val body = response.body?.string() ?: ""
            if (!response.isSuccessful) {
                throw Exception("فشل تنفيذ العملية (${response.code}): ${response.message}")
            }
            return gson.fromJson(body.ifBlank { "{}" }, JsonObject::class.java) ?: JsonObject()
        }
    }

    suspend fun getAccessToken(forceRefresh: Boolean = false): String = withContext(Dispatchers.IO) {
        return@withContext "local-server-token"
    }

    /**
     * جلب قائمة الملفات والمجلدات داخل مجلد محدد من خادم Share COC المحلي
     */
    suspend fun listItems(
        parentId: String = AppConfig.rootFolderId,
        includeTrashed: Boolean = false
    ): List<DriveItem> = withContext(Dispatchers.IO) {
        val normParent = normalizeFolderId(parentId)
        val url = "${AppConfig.SERVER_BASE_URL}/api/drive/files".toHttpUrl().newBuilder()
            .addQueryParameter("refresh", "1")
            .addQueryParameter("t", System.currentTimeMillis().toString())
            .build()

        val request = Request.Builder()
            .url(url)
            .addHeader("x-admin-role", "admin")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل جلب الملفات من الخادم: ${response.code} ${response.message}")
            }
            val body = response.body?.string() ?: return@withContext emptyList()
            val json = gson.fromJson(body, JsonObject::class.java) ?: return@withContext emptyList()
            val result = mutableListOf<DriveItem>()

            val allFolders = json.getAsJsonArray("allFolders")
            var currentFolderPath = decodeFolderPath(normParent)
            if (currentFolderPath.isBlank() && normParent != "root" && allFolders != null) {
                for (el in allFolders) {
                    val obj = el.asJsonObject
                    if (obj.get("id")?.asString == normParent) {
                        currentFolderPath = obj.get("path")?.asString ?: ""
                        break
                    }
                }
            }

            if (!includeTrashed && allFolders != null) {
                for (el in allFolders) {
                    val fObj = el.asJsonObject
                    val fParentPath = fObj.get("parentPath")?.asString ?: ""
                    if (fParentPath == currentFolderPath) {
                        val fName = fObj.get("name")?.asString ?: continue
                        if (fName.startsWith(".") || fName.startsWith("~$")) continue
                        result.add(
                            DriveItem(
                                id = fObj.get("id")?.asString ?: "",
                                name = fName,
                                mimeType = AppConfig.FOLDER_MIME,
                                sizeString = null,
                                modifiedTime = fObj.get("modifiedTime")?.asString,
                                parents = listOf(normParent)
                            )
                        )
                    }
                }
            }

            val filesArray = json.getAsJsonArray("files")
            if (filesArray != null) {
                for (el in filesArray) {
                    val fObj = el.asJsonObject
                    val isDeleted = fObj.get("isDeleted")?.asBoolean ?: false
                    if (includeTrashed && !isDeleted) continue
                    if (!includeTrashed && isDeleted) continue

                    val fname = fObj.get("name")?.asString ?: continue
                    if (fname.startsWith("~$") || fname.startsWith(".") || fname.equals("desktop.ini", true)) {
                        continue
                    }

                    val itemFolderId = normalizeFolderId(fObj.get("folderId")?.asString ?: "root")
                    val itemFolder = fObj.get("folder")?.asString ?: ""
                    val matchesParent = if (includeTrashed) {
                        true
                    } else if (normParent == "root") {
                        itemFolderId == "root" || itemFolder == "القسم العام" || itemFolder.isBlank()
                    } else {
                        itemFolderId == normParent || itemFolder == currentFolderPath
                    }

                    if (!matchesParent) continue

                    result.add(
                        DriveItem(
                            id = fObj.get("id")?.asString ?: "",
                            name = fname,
                            mimeType = fObj.get("mimeType")?.asString ?: "application/octet-stream",
                            sizeString = fObj.get("size")?.asString,
                            md5Checksum = fObj.get("md5Checksum")?.asString,
                            modifiedTime = fObj.get("modifiedTime")?.asString,
                            parents = listOf(itemFolderId)
                        )
                    )
                }
            }

            return@withContext result
        }
    }

    /**
     * قراءة إعدادات الصلاحيات والأجهزة من /api/drive/permissions
     */
    suspend fun loadPermissionsConfig(): CloudAdminStore = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("${AppConfig.SERVER_BASE_URL}/api/drive/permissions?admin=1&force=1&t=${System.currentTimeMillis()}")
            .addHeader("x-admin-role", "admin")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return@withContext CloudAdminStore()
            val content = response.body?.string() ?: return@withContext CloudAdminStore()
            try {
                val raw = gson.fromJson(content, JsonObject::class.java) ?: return@withContext CloudAdminStore()
                val normalized = JsonObject().apply {
                    addProperty("version", 3)
                    add("departments", raw.get("permissions") ?: JsonObject())
                    raw.get("adminCredentials")?.let { add("adminCredentials", it) }
                    raw.get("devices")?.let { add("devices", it) }
                    raw.get("accessHubSecurity")?.let { add("accessHubSecurity", it) }
                }
                return@withContext gson.fromJson(normalized, CloudAdminStore::class.java)
            } catch (e: Exception) {
                Log.e(TAG, "خطأ في معالجة الصلاحيات: ${e.message}")
                return@withContext CloudAdminStore()
            }
        }
    }

    /**
     * حفظ وتحديث الصلاحيات والأجهزة عبر /api/drive/permissions
     */
    suspend fun savePermissionsConfig(store: CloudAdminStore): Boolean = withContext(Dispatchers.IO) {
        try {
            val permsPayload = JsonObject().apply {
                addProperty("isAdmin", true)
                add("permissions", gson.toJsonTree(store.departments))
            }
            val permsReq = Request.Builder()
                .url("${AppConfig.SERVER_BASE_URL}/api/drive/permissions")
                .addHeader("x-admin-role", "admin")
                .post(permsPayload.toString().toRequestBody(jsonMediaType))
                .build()
            val permsOk = client.newCall(permsReq).execute().use { it.isSuccessful }

            val devsPayload = JsonObject().apply {
                addProperty("action", "SAVE_DEVICES")
                addProperty("isAdmin", true)
                add("devices", gson.toJsonTree(store.devices))
            }
            val devsReq = Request.Builder()
                .url("${AppConfig.SERVER_BASE_URL}/api/drive/permissions")
                .addHeader("x-admin-role", "admin")
                .post(devsPayload.toString().toRequestBody(jsonMediaType))
                .build()
            val devsOk = client.newCall(devsReq).execute().use { it.isSuccessful }

            return@withContext permsOk && devsOk
        } catch (e: Exception) {
            Log.e(TAG, "خطأ حفظ الصلاحيات: ${e.message}")
            return@withContext false
        }
    }

    /**
     * تنزيل ملف من /api/drive/stream مع مؤشر تقدم
     */
    suspend fun downloadFile(
        fileId: String,
        destinationFile: File,
        onProgress: (Float) -> Unit = {}
    ): Boolean = withContext(Dispatchers.IO) {
        val encodedId = URLEncoder.encode(fileId, "UTF-8")
        val url = "${AppConfig.SERVER_BASE_URL}/api/drive/stream?id=$encodedId&download=1"

        val request = Request.Builder()
            .url(url)
            .addHeader("x-admin-role", "admin")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل تنزيل الملف: ${response.code} ${response.message}")
            }
            val body = response.body ?: throw Exception("بيانات الملف فارغة")
            val headerSize = response.header("X-File-Size")?.toLongOrNull() ?: body.contentLength()
            var downloadedBytes = 0L

            destinationFile.parentFile?.mkdirs()
            FileOutputStream(destinationFile).use { output ->
                body.byteStream().use { input ->
                    val buffer = ByteArray(64 * 1024)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        downloadedBytes += read
                        if (headerSize > 0) {
                            onProgress(downloadedBytes.toFloat() / headerSize.toFloat())
                        }
                    }
                    output.flush()
                }
            }
            onProgress(1.0f)
            return@withContext true
        }
    }

    private fun uploadChunkedToFolder(
        folderId: String,
        folderPath: String,
        file: File,
        mimeType: String,
        onProgress: (Float) -> Unit
    ): DriveItem {
        val fileSize = file.length()
        val initPayload = JsonObject().apply {
            addProperty("action", "INIT_UPLOAD")
            addProperty("fileName", file.name)
            addProperty("mimeType", mimeType)
            addProperty("fileSize", fileSize)
            addProperty("folderId", folderId)
            if (folderPath.isNotBlank()) addProperty("folderPath", folderPath)
        }
        val initRes = postJsonAction(initPayload)
        val sessionUri = initRes.get("sessionUri")?.asString
            ?: throw Exception("لم يتم استلام معرف جلسة الرفع sessionUri")

        val chunkSize = AppConfig.CHUNK_SIZE_BYTES
        var uploadedBytes = 0L
        val raf = RandomAccessFile(file, "r")
        val buffer = ByteArray(chunkSize)

        try {
            while (uploadedBytes < fileSize) {
                val currentChunkLength = Math.min(chunkSize.toLong(), fileSize - uploadedBytes).toInt()
                raf.seek(uploadedBytes)
                raf.readFully(buffer, 0, currentChunkLength)

                val chunkBody = buffer.toRequestBody("application/octet-stream".toMediaType(), 0, currentChunkLength)
                val endByte = uploadedBytes + currentChunkLength - 1

                val multipart = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("action", "UPLOAD_CHUNK")
                    .addFormDataPart("sessionUri", sessionUri)
                    .addFormDataPart("start", uploadedBytes.toString())
                    .addFormDataPart("end", endByte.toString())
                    .addFormDataPart("total", fileSize.toString())
                    .addFormDataPart("chunk", file.name, chunkBody)
                    .build()

                val chunkRequest = Request.Builder()
                    .url("${AppConfig.SERVER_BASE_URL}/api/drive/files")
                    .addHeader("x-admin-role", "admin")
                    .post(multipart)
                    .build()

                client.newCall(chunkRequest).execute().use { response ->
                    val body = response.body?.string() ?: ""
                    if (!response.isSuccessful) {
                        throw Exception("خطأ أثناء رفع شريحة الملف: ${response.code} ${response.message}")
                    }
                    val resJson = gson.fromJson(body, JsonObject::class.java)
                    uploadedBytes += currentChunkLength
                    onProgress(uploadedBytes.toFloat() / Math.max(fileSize, 1L).toFloat())
                    if (resJson.get("done")?.asBoolean == true && resJson.has("file")) {
                        onProgress(1.0f)
                        return gson.fromJson(resJson.getAsJsonObject("file"), DriveItem::class.java)
                    }
                }
            }
        } finally {
            raf.close()
        }

        throw Exception("انتهى الرفع دون استلام بيانات الملف النهائية")
    }

    /**
     * رفع ملف إلى خادم Share COC مع دعم الرفع المجزأ القابل للاستئناف
     */
    suspend fun uploadFile(
        parentId: String,
        file: File,
        mimeType: String,
        onProgress: (Float) -> Unit = {}
    ): DriveItem = withContext(Dispatchers.IO) {
        val normParent = normalizeFolderId(parentId)
        val folderPath = decodeFolderPath(normParent)
        val fileSize = file.length()

        if (fileSize <= AppConfig.CHUNK_SIZE_BYTES) {
            val fileBody = file.asRequestBody(mimeType.toMediaType())
            val mb = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("fileName", file.name)
                .addFormDataPart("folderId", normParent)
                .addFormDataPart("file", file.name, fileBody)
            if (folderPath.isNotBlank()) {
                mb.addFormDataPart("folderPath", folderPath)
            }

            val request = Request.Builder()
                .url("${AppConfig.SERVER_BASE_URL}/api/drive/files")
                .addHeader("x-admin-role", "admin")
                .post(mb.build())
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw Exception("فشل رفع الملف: ${response.code} ${response.message}")
                }
                val body = response.body?.string() ?: throw Exception("استجابة الرفع فارغة")
                val json = gson.fromJson(body, JsonObject::class.java)
                val fileObj = json.getAsJsonObject("file") ?: json
                onProgress(1.0f)
                return@withContext gson.fromJson(fileObj, DriveItem::class.java)
            }
        }

        return@withContext uploadChunkedToFolder(normParent, folderPath, file, mimeType, onProgress)
    }

    /**
     * تحديث محتوى ملف موجود على الخادم فور الحفظ في تطبيق Office
     */
    suspend fun updateFileContent(
        fileId: String,
        file: File,
        mimeType: String,
        onProgress: (Float) -> Unit = {}
    ): DriveItem = withContext(Dispatchers.IO) {
        val fileSize = file.length()
        if (fileSize <= 8L * 1024L * 1024L) {
            val encodedId = URLEncoder.encode(fileId, "UTF-8")
            val encodedName = URLEncoder.encode(file.name, "UTF-8")
            val request = Request.Builder()
                .url("${AppConfig.SERVER_BASE_URL}/api/drive/file/$encodedId/$encodedName")
                .addHeader("x-admin-role", "admin")
                .put(file.asRequestBody(mimeType.toMediaType()))
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw Exception("فشل تحديث المستند: ${response.code} ${response.message}")
                }
                onProgress(1.0f)
                return@withContext DriveItem(
                    id = fileId,
                    name = file.name,
                    mimeType = mimeType,
                    sizeString = fileSize.toString()
                )
            }
        }

        val relPath = decodeFolderPath(fileId)
        val parentRel = if (relPath.contains("/")) relPath.substringBeforeLast("/") else ""
        return@withContext uploadChunkedToFolder("root", parentRel, file, mimeType, onProgress)
    }

    /**
     * إنشاء مجلد جديد عبر /api/drive/files
     */
    suspend fun createFolder(parentId: String, name: String): DriveItem = withContext(Dispatchers.IO) {
        val payload = JsonObject().apply {
            addProperty("action", "CREATE_FOLDER")
            addProperty("name", name)
            addProperty("parentId", normalizeFolderId(parentId))
        }
        val res = postJsonAction(payload)
        val folderObj = res.getAsJsonObject("folder")
            ?: throw Exception("استجابة إنشاء المجلد فارغة")
        return@withContext gson.fromJson(folderObj, DriveItem::class.java)
    }

    /**
     * إعادة تسمية عنصر
     */
    suspend fun renameItem(itemId: String, newName: String): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val payload = JsonObject().apply {
                addProperty("action", "RENAME")
                addProperty("id", itemId)
                addProperty("name", newName)
            }
            postJsonAction(payload)
            true
        } catch (e: Exception) {
            Log.e(TAG, "renameItem error: ${e.message}")
            false
        }
    }

    /**
     * نقل عنصر إلى سلة المحذوفات (Soft Delete)
     */
    suspend fun trashItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val payload = JsonObject().apply {
                addProperty("action", "DELETE")
                addProperty("id", itemId)
            }
            postJsonAction(payload)
            true
        } catch (e: Exception) {
            Log.e(TAG, "trashItem error: ${e.message}")
            false
        }
    }

    /**
     * استعادة عنصر من سلة المحذوفات (Restore)
     */
    suspend fun restoreItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val payload = JsonObject().apply {
                addProperty("action", "RESTORE")
                addProperty("id", itemId)
            }
            postJsonAction(payload)
            true
        } catch (e: Exception) {
            Log.e(TAG, "restoreItem error: ${e.message}")
            false
        }
    }

    /**
     * حذف عنصر نهائياً (Permanent Delete)
     */
    suspend fun permanentDeleteItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        return@withContext try {
            val payload = JsonObject().apply {
                addProperty("action", "PERMANENT_DELETE")
                addProperty("id", itemId)
            }
            postJsonAction(payload)
            true
        } catch (e: Exception) {
            Log.e(TAG, "permanentDeleteItem error: ${e.message}")
            false
        }
    }
}
