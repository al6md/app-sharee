package iq.sharecoc.app.office

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import android.widget.Toast
import androidx.core.content.FileProvider
import iq.sharecoc.app.config.AppConfig
import java.io.File

object OfficeLauncher {

    private const val TAG = "OfficeLauncher"
    private const val FILE_PROVIDER_AUTHORITY = "iq.sharecoc.app.fileprovider"

    /**
     * فتح الملف المُنزل محلياً في التطبيق الأصلي المتوافق (Word, Excel, PowerPoint, PDF, etc.)
     */
    fun openInNativeOffice(context: Context, localFile: File): Boolean {
        if (!localFile.exists()) {
            Toast.makeText(context, "الملف غير موجود محلياً", Toast.LENGTH_SHORT).show()
            return false
        }

        try {
            val ext = localFile.extension.lowercase()
            val mime = AppConfig.getMimeForExtension(ext)
            val uri: Uri = FileProvider.getUriForFile(context, FILE_PROVIDER_AUTHORITY, localFile)

            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, mime)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }

            // محاولة فتح التطبيق
            if (intent.resolveActivity(context.packageManager) != null) {
                context.startActivity(intent)
                return true
            } else {
                // إذا لم يوجد تطبيق افتراضي، نعرض نافذة الاختيار
                val chooser = Intent.createChooser(intent, "اختر التطبيق لفتح المستند").apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(chooser)
                return true
            }
        } catch (e: Exception) {
            Log.e(TAG, "خطأ أثناء محاولة فتح ملف Office: ${e.message}", e)
            Toast.makeText(context, "تعذر فتح المستند: ${e.localizedMessage}", Toast.LENGTH_LONG).show()
            return false
        }
    }
}
