package iq.sharecoc.app

import android.os.Bundle
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.fragment.app.FragmentActivity
import iq.sharecoc.app.ui.screens.MainExplorerScreen
import iq.sharecoc.app.ui.theme.ShareCOCTheme
import iq.sharecoc.app.ui.viewmodel.DriveViewModel

class MainActivity : FragmentActivity() {

    private val driveViewModel: DriveViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // التعامل مع زر الرجوع للتنقل بين مجلدات Google Drive
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val handled = driveViewModel.navigateBack()
                if (!handled) {
                    finish()
                }
            }
        })

        setContent {
            ShareCOCTheme {
                MainExplorerScreen(viewModel = driveViewModel)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // فحص أي تعديل تم حفظه في تطبيق Word / Excel / WPS ومزامنته تلقائياً فور العودة
        driveViewModel.checkAndSyncWatchedFile()
    }
}
