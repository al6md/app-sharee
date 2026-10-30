package iq.sharecoc.app

import android.app.Application
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import iq.sharecoc.app.config.AppConfig
import java.io.InputStreamReader

class ShareCocApplication : Application() {

    companion object {
        private const val TAG = "ShareCocApplication"
    }

    override fun onCreate() {
        super.onCreate()
        loadCredentialsFromAssets()
    }

    private fun loadCredentialsFromAssets() {
        try {
            assets.open("gdrive_credentials.json").use { inputStream ->
                val json = Gson().fromJson(InputStreamReader(inputStream), JsonObject::class.java)
                if (json.has("client_id")) {
                    AppConfig.clientId = json.get("client_id").asString
                }
                if (json.has("client_secret")) {
                    AppConfig.clientSecret = json.get("client_secret").asString
                }
                if (json.has("refresh_token")) {
                    AppConfig.refreshToken = json.get("refresh_token").asString
                }
                if (json.has("folder_id")) {
                    AppConfig.rootFolderId = json.get("folder_id").asString
                }
                Log.d(TAG, "تم تحميل بيانات Google Drive من assets بنجاح. المجلد: ${AppConfig.rootFolderId}")
            }
        } catch (e: Exception) {
            Log.w(TAG, "تعذر قراءة gdrive_credentials.json من assets، سيتم استخدام الإعدادات المدمجة: ${e.message}")
        }
    }
}
