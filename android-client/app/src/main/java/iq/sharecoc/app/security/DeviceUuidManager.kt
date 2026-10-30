package iq.sharecoc.app.security

import android.content.Context
import android.os.Build
import android.provider.Settings
import iq.sharecoc.app.data.models.AuthorizedDeviceConfig
import iq.sharecoc.app.data.network.GoogleDriveApiClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.security.MessageDigest
import java.util.UUID

object DeviceUuidManager {

    private const val PREFS_NAME = "sharecoc_device_prefs"
    private const val KEY_MACHINE_GUID = "machine_guid"

    /**
     * استخراج وتثبيت رقم تعريف فريد للجهاز (Hardware GUID)
     */
    fun getOrCreateDeviceGuid(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        var guid = prefs.getString(KEY_MACHINE_GUID, null)
        if (guid != null) return guid

        // استخدام Android ID كأساس مستقر
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: ""
        guid = if (androidId.isNotBlank() && androidId != "9774d56d682e549c") {
            "COC-AND-" + hashSha256(androidId).substring(0, 12).uppercase()
        } else {
            "COC-AND-" + UUID.randomUUID().toString().substring(0, 12).uppercase()
        }

        prefs.edit().putString(KEY_MACHINE_GUID, guid).apply()
        return guid
    }

    /**
     * التحقق من حالة اعتماد الجهاز على سحابة Google Drive، وتسجيله تلقائياً إذا كان جهازاً جديداً
     */
    suspend fun verifyAndRegisterDevice(context: Context, deviceUserName: String = "مستخدم الهاتف"): Boolean = withContext(Dispatchers.IO) {
        val guid = getOrCreateDeviceGuid(context)
        val apiClient = GoogleDriveApiClient.getInstance()
        val store = apiClient.loadPermissionsConfig()

        val existing = store.devices.find { it.machineGuid.equals(guid, ignoreCase = true) }
        val deviceModel = "${Build.MANUFACTURER.uppercase()} ${Build.MODEL}"

        if (existing != null) {
            // تحديث حالة آخر ظهور
            existing.lastSeen = "متصل الآن"
            existing.status = "متصل الآن"
            apiClient.savePermissionsConfig(store)
            return@withContext existing.isAuthorized
        } else {
            // تسجيل جهاز هاتف جديد بانتظار اعتماد الإدارة
            val newDevice = AuthorizedDeviceConfig(
                id = "dev-mob-" + UUID.randomUUID().toString().substring(0, 6),
                name = deviceModel,
                user = deviceUserName,
                os = "Android " + Build.VERSION.RELEASE,
                machineGuid = guid,
                isAuthorized = true, // معتمد افتراضياً أو يمكن ضبطه false حسب رغبة المؤسسة
                lastSeen = "متصل الآن",
                status = "متصل الآن"
            )
            store.devices.add(newDevice)
            apiClient.savePermissionsConfig(store)
            return@withContext true
        }
    }

    private fun hashSha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }
}
