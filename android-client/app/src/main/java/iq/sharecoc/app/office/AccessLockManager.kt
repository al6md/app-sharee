package iq.sharecoc.app.office

import android.util.Log
import iq.sharecoc.app.config.AppConfig
import iq.sharecoc.app.data.network.GoogleDriveApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

object AccessLockManager {

    private const val TAG = "AccessLockManager"
    private const val DEFAULT_LOCAL_BRIDGE_PORT = 18290

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /**
     * إرسال أمر لجهاز الكمبيوتر في المكتب لفتح الملف فورياً على الشاشة الكبيرة
     * عبر منفذ الجسر المحلي Port 18290 (Local Companion Bridge)
     */
    suspend fun launchOnRemotePC(pcIpAddress: String, relativeFilePath: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val encodedPath = URLEncoder.encode(relativeFilePath, "UTF-8")
            val url = "http://$pcIpAddress:$DEFAULT_LOCAL_BRIDGE_PORT/open?file=$encodedPath"

            val request = Request.Builder()
                .url(url)
                .get()
                .build()

            httpClient.newCall(request).execute().use { response ->
                Log.d(TAG, "استجابة الجسر المساعد للحاسوب: ${response.code}")
                return@withContext response.isSuccessful
            }
        } catch (e: Exception) {
            Log.e(TAG, "فشل الاتصال بجهاز الحاسوب $pcIpAddress: ${e.message}")
            return@withContext false
        }
    }

    /**
     * حجز حصري لقاعدة بيانات Access على سحابة Google Drive لحمايتها من التعديل المزدوج
     */
    suspend fun lockDatabase(fileId: String, fileName: String, deviceName: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val apiClient = GoogleDriveApiClient.getInstance()
            val store = apiClient.loadPermissionsConfig()

            // تسجيل القفل داخل ملف التهيئة السحابي المشترك
            val lockKey = "lock_$fileId"
            store.departments[lockKey] = iq.sharecoc.app.data.models.DepartmentPermissionConfig(
                departmentName = "LOCKED_BY_$deviceName",
                pinCode = fileName,
                updatedAt = System.currentTimeMillis().toString()
            )

            apiClient.savePermissionsConfig(store)
            return@withContext true
        } catch (e: Exception) {
            Log.e(TAG, "خطأ أثناء حجز قاعدة بيانات Access: ${e.message}")
            return@withContext false
        }
    }

    /**
     * فك حجز قاعدة بيانات Access بعد انتهاء العمل
     */
    suspend fun unlockDatabase(fileId: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val apiClient = GoogleDriveApiClient.getInstance()
            val store = apiClient.loadPermissionsConfig()
            val lockKey = "lock_$fileId"

            if (store.departments.containsKey(lockKey)) {
                store.departments.remove(lockKey)
                apiClient.savePermissionsConfig(store)
            }
            return@withContext true
        } catch (e: Exception) {
            Log.e(TAG, "خطأ أثناء فك حجز قاعدة البيانات: ${e.message}")
            return@withContext false
        }
    }
}
