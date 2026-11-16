package iq.sharecoc.app

import android.app.Application
import android.util.Log
import iq.sharecoc.app.config.AppConfig

class ShareCocApplication : Application() {

    companion object {
        private const val TAG = "ShareCocApplication"
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(
            TAG,
            "تم تهيئة ${AppConfig.APP_NAME} للاتصال بسيرفر Share COC (${AppConfig.SERVER_BASE_URL})، المجلد: ${AppConfig.rootFolderId}"
        )
    }
}
