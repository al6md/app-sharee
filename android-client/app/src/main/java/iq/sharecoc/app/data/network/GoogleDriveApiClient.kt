package iq.sharecoc.app.data.network

import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import iq.sharecoc.app.config.AppConfig
import iq.sharecoc.app.data.models.CloudAdminStore
import iq.sharecoc.app.data.models.DriveItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.util.concurrent.TimeUnit

class GoogleDriveApiClient private constructor() {

    companion object {
        private const val TAG = "GoogleDriveApiClient"

        @Volatile
        private var instance: GoogleDriveApiClient? = null

        fun getInstance(): GoogleDriveApiClient {
            return instance ?: synchronized(this) {
                instance ?: GoogleDriveApiClient().also { instance = it }
            }
        }
    }

    private val gson = Gson()
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(AppConfig.CONNECT_TIMEOUT_SEC, TimeUnit.SECONDS)
        .readTimeout(AppConfig.READ_TIMEOUT_SEC, TimeUnit.SECONDS)
        .writeTimeout(AppConfig.READ_TIMEOUT_SEC, TimeUnit.SECONDS)
        .build()

    private var currentAccessToken: String? = null
    private var tokenExpiryTimeMs: Long = 0

    /**
     * تجديد واستخراج Access Token من خلال الـ Refresh Token المعتمد
     */
    suspend fun getAccessToken(forceRefresh: Boolean = false): String = withContext(Dispatchers.IO) {
        val now = System.currentTimeMillis()
        if (!forceRefresh && currentAccessToken != null && now < tokenExpiryTimeMs - 60_000) {
            return@withContext currentAccessToken!!
        }

        val formBody = FormBody.Builder()
            .add("client_id", AppConfig.clientId)
            .add("client_secret", AppConfig.clientSecret)
            .add("refresh_token", AppConfig.refreshToken)
            .add("grant_type", "refresh_token")
            .build()

        val request = Request.Builder()
            .url(AppConfig.OAUTH_TOKEN_URL)
            .post(formBody)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل تجديد توكن الوصول إلى Google Drive: ${response.code} ${response.message}")
            }
            val body = response.body?.string() ?: throw Exception("استجابة التوكن فارغة")
            val json = gson.fromJson(body, JsonObject::class.java)
            val token = json.get("access_token").asString
            val expiresInSec = json.get("expires_in")?.asLong ?: 3600L

            currentAccessToken = token
            tokenExpiryTimeMs = now + (expiresInSec * 1000)
            Log.d(TAG, "تم تجديد Google Drive Access Token بنجاح. الصلاحية: $expiresInSec ثانية")
            return@withContext token
        }
    }

    /**
     * جلب قائمة الملفات والمجلدات داخل مجلد محدد (أو الجذر الافتراضي)
     */
    suspend fun listItems(
        parentId: String = AppConfig.rootFolderId,
        includeTrashed: Boolean = false
    ): List<DriveItem> = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val trashedQuery = if (includeTrashed) "trashed = true" else "trashed = false"
        val q = "'$parentId' in parents and $trashedQuery"

        val url = "${AppConfig.DRIVE_API_BASE_URL}/files".toHttpUrl().newBuilder()
            .addQueryParameter("q", q)
            .addQueryParameter("pageSize", "200")
            .addQueryParameter("fields", "files(id, name, mimeType, size, md5Checksum, modifiedTime, createdTime, parents)")
            .addQueryParameter("orderBy", "folder,name_natural")
            .build()

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $token")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل جلب الملفات من Google Drive: ${response.code} ${response.message}")
            }
            val body = response.body?.string() ?: return@withContext emptyList()
            val json = gson.fromJson(body, JsonObject::class.java)
            val filesArray = json.getAsJsonArray("files") ?: return@withContext emptyList()

            val items = mutableListOf<DriveItem>()
            for (element in filesArray) {
                val item = gson.fromJson(element, DriveItem::class.java)
                // تجاهل ملفات النظام المؤقتة وملف الصلاحيات من القائمة العادية
                if (!item.name.startsWith("~$") && !item.name.startsWith(".") && item.name != "desktop.ini") {
                    items.add(item)
                }
            }
            return@withContext items
        }
    }

    /**
     * قراءة ملف الصلاحيات والأجهزة المشترك (.sharecoc_permissions.json)
     */
    suspend fun loadPermissionsConfig(): CloudAdminStore = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val q = "'${AppConfig.rootFolderId}' in parents and name = '${AppConfig.PERMISSIONS_CONFIG_FILENAME}' and trashed = false"

        val url = "${AppConfig.DRIVE_API_BASE_URL}/files".toHttpUrl().newBuilder()
            .addQueryParameter("q", q)
            .addQueryParameter("fields", "files(id, name)")
            .build()

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $token")
            .get()
            .build()

        var fileId: String? = null
        client.newCall(request).execute().use { response ->
            if (response.isSuccessful) {
                val body = response.body?.string() ?: ""
                val json = gson.fromJson(body, JsonObject::class.java)
                val files = json.getAsJsonArray("files")
                if (files != null && files.size() > 0) {
                    fileId = files[0].asJsonObject.get("id").asString
                }
            }
        }

        if (fileId == null) {
            return@withContext CloudAdminStore()
        }

        // تنزيل محتوى الملف وقراءته
        val downloadUrl = "${AppConfig.DRIVE_API_BASE_URL}/files/$fileId?alt=media"
        val dlRequest = Request.Builder()
            .url(downloadUrl)
            .addHeader("Authorization", "Bearer $token")
            .get()
            .build()

        client.newCall(dlRequest).execute().use { response ->
            if (!response.isSuccessful) return@withContext CloudAdminStore()
            val content = response.body?.string() ?: return@withContext CloudAdminStore()
            try {
                return@withContext gson.fromJson(content, CloudAdminStore::class.java)
            } catch (e: Exception) {
                Log.e(TAG, "خطأ في معالجة ملف الصلاحيات: ${e.message}")
                return@withContext CloudAdminStore()
            }
        }
    }

    /**
     * حفظ وتحديث ملف الصلاحيات والأجهزة المشترك (.sharecoc_permissions.json)
     */
    suspend fun savePermissionsConfig(store: CloudAdminStore): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val jsonContent = gson.toJson(store)

        // البحث أولاً إن كان الملف موجوداً
        val q = "'${AppConfig.rootFolderId}' in parents and name = '${AppConfig.PERMISSIONS_CONFIG_FILENAME}' and trashed = false"
        val searchUrl = "${AppConfig.DRIVE_API_BASE_URL}/files".toHttpUrl().newBuilder()
            .addQueryParameter("q", q)
            .addQueryParameter("fields", "files(id)")
            .build()

        var existingId: String? = null
        client.newCall(Request.Builder().url(searchUrl).addHeader("Authorization", "Bearer $token").get().build())
            .execute().use { response ->
                if (response.isSuccessful) {
                    val body = response.body?.string() ?: ""
                    val json = gson.fromJson(body, JsonObject::class.java)
                    val files = json.getAsJsonArray("files")
                    if (files != null && files.size() > 0) {
                        existingId = files[0].asJsonObject.get("id").asString
                    }
                }
            }

        val requestBody = jsonContent.toRequestBody("application/json; charset=utf-8".toMediaType())

        if (existingId != null) {
            val updateUrl = "${AppConfig.DRIVE_UPLOAD_BASE_URL}/files/$existingId?uploadType=media"
            val updateRequest = Request.Builder()
                .url(updateUrl)
                .addHeader("Authorization", "Bearer $token")
                .patch(requestBody)
                .build()
            return@withContext client.newCall(updateRequest).execute().isSuccessful
        } else {
            val metadata = JsonObject().apply {
                addProperty("name", AppConfig.PERMISSIONS_CONFIG_FILENAME)
                addProperty("mimeType", "application/json")
                add("parents", gson.toJsonTree(listOf(AppConfig.rootFolderId)))
            }
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("metadata", null, metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
                .addFormDataPart("media", AppConfig.PERMISSIONS_CONFIG_FILENAME, requestBody)
                .build()

            val createUrl = "${AppConfig.DRIVE_UPLOAD_BASE_URL}/files?uploadType=multipart"
            val createRequest = Request.Builder()
                .url(createUrl)
                .addHeader("Authorization", "Bearer $token")
                .post(multipart)
                .build()
            return@withContext client.newCall(createRequest).execute().isSuccessful
        }
    }

    /**
     * تنزيل ملف من Google Drive مع مؤشر تقدم
     */
    suspend fun downloadFile(
        fileId: String,
        destinationFile: File,
        onProgress: (Float) -> Unit = {}
    ): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val url = "${AppConfig.DRIVE_API_BASE_URL}/files/$fileId?alt=media"

        val request = Request.Builder()
            .url(url)
            .addHeader("Authorization", "Bearer $token")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل تنزيل الملف: ${response.code} ${response.message}")
            }
            val body = response.body ?: throw Exception("بيانات الملف فارغة")
            val totalBytes = body.contentLength()
            var downloadedBytes = 0L

            destinationFile.parentFile?.mkdirs()
            FileOutputStream(destinationFile).use { output ->
                body.byteStream().use { input ->
                    val buffer = ByteArray(64 * 1024)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        downloadedBytes += read
                        if (totalBytes > 0) {
                            onProgress(downloadedBytes.toFloat() / totalBytes.toFloat())
                        }
                    }
                    output.flush()
                }
            }
            onProgress(1.0f)
            return@withContext true
        }
    }

    /**
     * رفع ملف إلى Google Drive مع دعم الرفع المجزأ القابل للاستئناف (Resumable Upload)
     */
    suspend fun uploadFile(
        parentId: String,
        file: File,
        mimeType: String,
        onProgress: (Float) -> Unit = {}
    ): DriveItem = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val fileSize = file.length()

        // 1. للملفات الصغيرة (أقل من أو يساوي 2MB) -> رفع سريع أحادي (Single-Shot Multipart)
        if (fileSize <= AppConfig.CHUNK_SIZE_BYTES) {
            val metadata = JsonObject().apply {
                addProperty("name", file.name)
                addProperty("mimeType", mimeType)
                add("parents", gson.toJsonTree(listOf(parentId)))
            }

            val fileBody = file.asRequestBody(mimeType.toMediaType())
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("metadata", null, metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
                .addFormDataPart("file", file.name, fileBody)
                .build()

            val request = Request.Builder()
                .url("${AppConfig.DRIVE_UPLOAD_BASE_URL}/files?uploadType=multipart&fields=id,name,mimeType,size,md5Checksum,modifiedTime")
                .addHeader("Authorization", "Bearer $token")
                .post(multipart)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw Exception("فشل رفع الملف: ${response.code} ${response.message}")
                }
                val body = response.body?.string() ?: throw Exception("استجابة الرفع فارغة")
                onProgress(1.0f)
                return@withContext gson.fromJson(body, DriveItem::class.java)
            }
        }

        // 2. للملفات الكبيرة (> 2MB) -> رفع مجزأ قابل للاستئناف (True Resumable Chunked Upload)
        val initMetadata = JsonObject().apply {
            addProperty("name", file.name)
            addProperty("mimeType", mimeType)
            add("parents", gson.toJsonTree(listOf(parentId)))
        }

        val initRequest = Request.Builder()
            .url("${AppConfig.DRIVE_UPLOAD_BASE_URL}/files?uploadType=resumable")
            .addHeader("Authorization", "Bearer $token")
            .addHeader("X-Upload-Content-Type", mimeType)
            .addHeader("X-Upload-Content-Length", fileSize.toString())
            .post(initMetadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        val sessionUri: String = client.newCall(initRequest).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل بدء جلسة الرفع المجزأ: ${response.code} ${response.message}")
            }
            response.header("Location") ?: throw Exception("لم يتم استلام عنوان جلسة الرفع Location")
        }

        // رفع الشرائح (Chunks)
        val chunkSize = AppConfig.CHUNK_SIZE_BYTES
        var uploadedBytes = 0L
        val raf = RandomAccessFile(file, "r")
        val buffer = ByteArray(chunkSize)

        try {
            while (uploadedBytes < fileSize) {
                val currentChunkLength = Math.min(chunkSize.toLong(), fileSize - uploadedBytes).toInt()
                raf.seek(uploadedBytes)
                raf.readFully(buffer, 0, currentChunkLength)

                val chunkBody = buffer.toRequestBody(mimeType.toMediaType(), 0, currentChunkLength)
                val contentRange = "bytes $uploadedBytes-${uploadedBytes + currentChunkLength - 1}/$fileSize"

                val chunkRequest = Request.Builder()
                    .url(sessionUri)
                    .addHeader("Content-Length", currentChunkLength.toString())
                    .addHeader("Content-Range", contentRange)
                    .put(chunkBody)
                    .build()

                client.newCall(chunkRequest).execute().use { response ->
                    if (response.code == 308) {
                        // الشريحة تم استقبالها، استمرار الرفع
                        uploadedBytes += currentChunkLength
                        onProgress(uploadedBytes.toFloat() / fileSize.toFloat())
                    } else if (response.isSuccessful) {
                        // اكتمل رفع جميع الشرائح بنجاح
                        uploadedBytes += currentChunkLength
                        onProgress(1.0f)
                        val body = response.body?.string() ?: ""
                        return@withContext gson.fromJson(body, DriveItem::class.java)
                    } else {
                        throw Exception("خطأ أثناء رفع شريحة الملف: ${response.code} ${response.message}")
                    }
                }
            }
        } finally {
            raf.close()
        }

        throw Exception("انتهى الرفع دون الحصول على كائن الملف النهائي")
    }

    /**
     * تحديث محتوى ملف موجود في Google Drive فور الحفظ في تطبيق Office (PATCH Update)
     */
    suspend fun updateFileContent(
        fileId: String,
        file: File,
        mimeType: String,
        onProgress: (Float) -> Unit = {}
    ): DriveItem = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val fileSize = file.length()

        // 1. للملفات الصغيرة (<= 2MB) -> PATCH مباشر فائق السرعة
        if (fileSize <= AppConfig.CHUNK_SIZE_BYTES) {
            val fileBody = file.asRequestBody(mimeType.toMediaType())
            val request = Request.Builder()
                .url("${AppConfig.DRIVE_UPLOAD_BASE_URL}/files/$fileId?uploadType=media&fields=id,name,mimeType,size,md5Checksum,modifiedTime")
                .addHeader("Authorization", "Bearer $token")
                .patch(fileBody)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    throw Exception("فشل تحديث المستند: ${response.code} ${response.message}")
                }
                val body = response.body?.string() ?: throw Exception("استجابة التحديث فارغة")
                onProgress(1.0f)
                return@withContext gson.fromJson(body, DriveItem::class.java)
            }
        }

        // 2. للملفات الكبيرة -> جلسة تحديث قابلة للاستئناف (Resumable PATCH)
        val initRequest = Request.Builder()
            .url("${AppConfig.DRIVE_UPLOAD_BASE_URL}/files/$fileId?uploadType=resumable")
            .addHeader("Authorization", "Bearer $token")
            .addHeader("X-Upload-Content-Type", mimeType)
            .addHeader("X-Upload-Content-Length", fileSize.toString())
            .patch("{}".toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        val sessionUri: String = client.newCall(initRequest).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل بدء جلسة تحديث الملف: ${response.code} ${response.message}")
            }
            response.header("Location") ?: throw Exception("لم يتم استلام عنوان جلسة التحديث Location")
        }

        val chunkSize = AppConfig.CHUNK_SIZE_BYTES
        var uploadedBytes = 0L
        val raf = RandomAccessFile(file, "r")
        val buffer = ByteArray(chunkSize)

        try {
            while (uploadedBytes < fileSize) {
                val currentChunkLength = Math.min(chunkSize.toLong(), fileSize - uploadedBytes).toInt()
                raf.seek(uploadedBytes)
                raf.readFully(buffer, 0, currentChunkLength)

                val chunkBody = buffer.toRequestBody(mimeType.toMediaType(), 0, currentChunkLength)
                val contentRange = "bytes $uploadedBytes-${uploadedBytes + currentChunkLength - 1}/$fileSize"

                val chunkRequest = Request.Builder()
                    .url(sessionUri)
                    .addHeader("Content-Length", currentChunkLength.toString())
                    .addHeader("Content-Range", contentRange)
                    .put(chunkBody)
                    .build()

                client.newCall(chunkRequest).execute().use { response ->
                    if (response.code == 308) {
                        uploadedBytes += currentChunkLength
                        onProgress(uploadedBytes.toFloat() / fileSize.toFloat())
                    } else if (response.isSuccessful) {
                        uploadedBytes += currentChunkLength
                        onProgress(1.0f)
                        val body = response.body?.string() ?: ""
                        return@withContext gson.fromJson(body, DriveItem::class.java)
                    } else {
                        throw Exception("خطأ أثناء تحديث شريحة الملف: ${response.code} ${response.message}")
                    }
                }
            }
        } finally {
            raf.close()
        }

        throw Exception("انتهى تحديث الملف دون استجابة نهائية")
    }

    /**
     * إنشاء مجلد جديد داخل Google Drive
     */
    suspend fun createFolder(parentId: String, name: String): DriveItem = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val metadata = JsonObject().apply {
            addProperty("name", name)
            addProperty("mimeType", AppConfig.FOLDER_MIME)
            add("parents", gson.toJsonTree(listOf(parentId)))
        }

        val request = Request.Builder()
            .url("${AppConfig.DRIVE_API_BASE_URL}/files?fields=id,name,mimeType,createdTime,parents")
            .addHeader("Authorization", "Bearer $token")
            .post(metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw Exception("فشل إنشاء المجلد: ${response.code} ${response.message}")
            }
            val body = response.body?.string() ?: throw Exception("استجابة إنشاء المجلد فارغة")
            return@withContext gson.fromJson(body, DriveItem::class.java)
        }
    }

    /**
     * إعادة تسمية عنصر
     */
    suspend fun renameItem(itemId: String, newName: String): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val metadata = JsonObject().apply {
            addProperty("name", newName)
        }
        val request = Request.Builder()
            .url("${AppConfig.DRIVE_API_BASE_URL}/files/$itemId")
            .addHeader("Authorization", "Bearer $token")
            .patch(metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        return@withContext client.newCall(request).execute().isSuccessful
    }

    /**
     * نقل عنصر إلى سلة المحذوفات (Soft Delete)
     */
    suspend fun trashItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val metadata = JsonObject().apply {
            addProperty("trashed", true)
        }
        val request = Request.Builder()
            .url("${AppConfig.DRIVE_API_BASE_URL}/files/$itemId")
            .addHeader("Authorization", "Bearer $token")
            .patch(metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        return@withContext client.newCall(request).execute().isSuccessful
    }

    /**
     * استعادة عنصر من سلة المحذوفات (Restore)
     */
    suspend fun restoreItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val metadata = JsonObject().apply {
            addProperty("trashed", false)
        }
        val request = Request.Builder()
            .url("${AppConfig.DRIVE_API_BASE_URL}/files/$itemId")
            .addHeader("Authorization", "Bearer $token")
            .patch(metadata.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()

        return@withContext client.newCall(request).execute().isSuccessful
    }

    /**
     * حذف عنصر نهائياً من Google Drive (Permanent Delete)
     */
    suspend fun permanentDeleteItem(itemId: String): Boolean = withContext(Dispatchers.IO) {
        val token = getAccessToken()
        val request = Request.Builder()
            .url("${AppConfig.DRIVE_API_BASE_URL}/files/$itemId")
            .addHeader("Authorization", "Bearer $token")
            .delete()
            .build()

        return@withContext client.newCall(request).execute().isSuccessful
    }
}
