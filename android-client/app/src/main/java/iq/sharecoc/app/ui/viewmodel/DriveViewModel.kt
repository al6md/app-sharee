package iq.sharecoc.app.ui.viewmodel

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import iq.sharecoc.app.config.AppConfig
import iq.sharecoc.app.data.models.CloudAdminStore
import iq.sharecoc.app.data.models.DepartmentPermissionConfig
import iq.sharecoc.app.data.models.DriveItem
import iq.sharecoc.app.data.network.GoogleDriveApiClient
import iq.sharecoc.app.office.AccessLockManager
import iq.sharecoc.app.security.DeviceUuidManager
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.io.File

data class FolderBreadcrumb(
    val id: String,
    val name: String
)

class DriveViewModel(application: Application) : AndroidViewModel(application) {

    private val TAG = "DriveViewModel"
    private val apiClient = GoogleDriveApiClient.getInstance()

    // الحالة العامة
    private val _items = MutableStateFlow<List<DriveItem>>(emptyList())
    val items: StateFlow<List<DriveItem>> = _items.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val _folderStack = MutableStateFlow<List<FolderBreadcrumb>>(listOf(FolderBreadcrumb(AppConfig.rootFolderId, "الرئيسية")))
    val folderStack: StateFlow<List<FolderBreadcrumb>> = _folderStack.asStateFlow()

    private val _adminStore = MutableStateFlow<CloudAdminStore>(CloudAdminStore())
    val adminStore: StateFlow<CloudAdminStore> = _adminStore.asStateFlow()

    private val _isDeviceAuthorized = MutableStateFlow(true)
    val isDeviceAuthorized: StateFlow<Boolean> = _isDeviceAuthorized.asStateFlow()

    private val _activeDownloadProgress = MutableStateFlow<Pair<String, Float>?>(null)
    val activeDownloadProgress: StateFlow<Pair<String, Float>?> = _activeDownloadProgress.asStateFlow()

    private val _activeUploadProgress = MutableStateFlow<Pair<String, Float>?>(null)
    val activeUploadProgress: StateFlow<Pair<String, Float>?> = _activeUploadProgress.asStateFlow()

    // محرك مراقبة التعديلات اللحظية في تطبيقات الموبايل والمزامنة التلقائية فور الحفظ
    private val _watchedItem = MutableStateFlow<DriveItem?>(null)
    val watchedItem: StateFlow<DriveItem?> = _watchedItem.asStateFlow()

    private val _watchedFile = MutableStateFlow<File?>(null)
    val watchedFile: StateFlow<File?> = _watchedFile.asStateFlow()

    private var watchedFileInitialMtime: Long = 0L

    private val _autoSyncStatus = MutableStateFlow<String>("")
    val autoSyncStatus: StateFlow<String> = _autoSyncStatus.asStateFlow()

    private val _autoSyncCount = MutableStateFlow<Int>(0)
    val autoSyncCount: StateFlow<Int> = _autoSyncCount.asStateFlow()

    private val _isAutoSyncing = MutableStateFlow<Boolean>(false)
    val isAutoSyncing: StateFlow<Boolean> = _isAutoSyncing.asStateFlow()

    private var watcherJob: Job? = null

    val currentFolderId: String
        get() = _folderStack.value.lastOrNull()?.id ?: AppConfig.rootFolderId

    val currentFolderName: String
        get() = _folderStack.value.lastOrNull()?.name ?: "الرئيسية"

    init {
        initializeClient()
    }

    fun initializeClient() {
        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null
            try {
                // 1. التحقق من الجهاز وتسجيله في سحابة Google Drive
                val isAuth = DeviceUuidManager.verifyAndRegisterDevice(getApplication())
                _isDeviceAuthorized.value = isAuth

                // 2. قراءة ملف الصلاحيات المشترك
                val store = apiClient.loadPermissionsConfig()
                _adminStore.value = store

                // 3. تحميل الملفات في المجلد الحالي
                loadFolderItems(currentFolderId)
            } catch (e: Exception) {
                Log.e(TAG, "خطأ التهيئة: ${e.message}", e)
                _errorMessage.value = e.localizedMessage ?: "فشل الاتصال بسحابة Google Drive"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun loadFolderItems(folderId: String = currentFolderId) {
        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null
            try {
                val fetchedItems = apiClient.listItems(parentId = folderId)

                // مطابقة أقفال ملفات Access المسجلة سحابياً
                val store = _adminStore.value
                val mappedItems = fetchedItems.map { item ->
                    val lockKey = "lock_${item.id}"
                    if (store.departments.containsKey(lockKey)) {
                        val lockConfig = store.departments[lockKey]
                        item.copy(isLocked = true, lockedBy = lockConfig?.departmentName?.removePrefix("LOCKED_BY_"))
                    } else {
                        item
                    }
                }

                _items.value = mappedItems
            } catch (e: Exception) {
                Log.e(TAG, "خطأ جلب محتويات المجلد: ${e.message}")
                _errorMessage.value = e.localizedMessage ?: "فشل تحديث قائمة الملفات"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun navigateToFolder(folderId: String, folderName: String) {
        val currentStack = _folderStack.value.toMutableList()
        currentStack.add(FolderBreadcrumb(folderId, folderName))
        _folderStack.value = currentStack
        loadFolderItems(folderId)
    }

    fun navigateBack(): Boolean {
        val currentStack = _folderStack.value.toMutableList()
        if (currentStack.size > 1) {
            currentStack.removeAt(currentStack.size - 1)
            _folderStack.value = currentStack
            loadFolderItems(currentFolderId)
            return true
        }
        return false
    }

    fun navigateToBreadcrumbIndex(index: Int) {
        val currentStack = _folderStack.value
        if (index in currentStack.indices && index < currentStack.size - 1) {
            _folderStack.value = currentStack.take(index + 1)
            loadFolderItems(currentFolderId)
        }
    }

    /**
     * تنزيل الملف محلياً وتحديث مؤشر التقدم
     */
    fun downloadFile(item: DriveItem, onComplete: (File) -> Unit) {
        viewModelScope.launch {
            val context = getApplication<Application>()
            val targetFile = File(context.cacheDir, "gdrive_${item.id}_${item.name}")

            _activeDownloadProgress.value = Pair(item.id, 0f)
            try {
                apiClient.downloadFile(item.id, targetFile) { progress ->
                    _activeDownloadProgress.value = Pair(item.id, progress)
                }
                _activeDownloadProgress.value = null
                onComplete(targetFile)
            } catch (e: Exception) {
                _activeDownloadProgress.value = null
                _errorMessage.value = "فشل تنزيل ${item.name}: ${e.message}"
            }
        }
    }

    /**
     * رفع ملف جديد أو ممسوح ضوئياً إلى Google Drive
     */
    fun uploadFile(file: File, mimeType: String, onUploaded: (DriveItem) -> Unit) {
        viewModelScope.launch {
            _activeUploadProgress.value = Pair(file.name, 0f)
            try {
                val createdItem = apiClient.uploadFile(currentFolderId, file, mimeType) { progress ->
                    _activeUploadProgress.value = Pair(file.name, progress)
                }
                _activeUploadProgress.value = null
                loadFolderItems(currentFolderId)
                onUploaded(createdItem)
            } catch (e: Exception) {
                _activeUploadProgress.value = null
                _errorMessage.value = "فشل رفع ${file.name}: ${e.message}"
            }
        }
    }

    /**
     * إنشاء مجلد جديد
     */
    fun createFolder(name: String) {
        viewModelScope.launch {
            _isLoading.value = true
            try {
                apiClient.createFolder(currentFolderId, name)
                loadFolderItems(currentFolderId)
            } catch (e: Exception) {
                _errorMessage.value = "فشل إنشاء المجلد: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * حجز قاعدة بيانات Access
     */
    fun lockAccessDatabase(item: DriveItem) {
        viewModelScope.launch {
            val deviceGuid = DeviceUuidManager.getOrCreateDeviceGuid(getApplication())
            val success = AccessLockManager.lockDatabase(item.id, item.name, deviceGuid)
            if (success) {
                loadFolderItems(currentFolderId)
            } else {
                _errorMessage.value = "فشل حجز قاعدة البيانات على السحابة"
            }
        }
    }

    /**
     * فك حجز قاعدة بيانات Access
     */
    fun unlockAccessDatabase(item: DriveItem) {
        viewModelScope.launch {
            val success = AccessLockManager.unlockDatabase(item.id)
            if (success) {
                loadFolderItems(currentFolderId)
            } else {
                _errorMessage.value = "فشل فك حجز قاعدة البيانات"
            }
        }
    }

    /**
     * إرسال أمر فتح الملف على كمبيوتر المكتب
     */
    fun launchOnRemoteOfficePC(pcIp: String, relativePath: String, onResult: (Boolean) -> Unit) {
        viewModelScope.launch {
            val success = AccessLockManager.launchOnRemotePC(pcIp, relativePath)
            onResult(success)
        }
    }

    fun clearError() {
        _errorMessage.value = null
    }

    /**
     * بدء مراقبة المستند وتشغيله في تطبيق الهاتف (Word / Excel / WPS)
     */
    fun startWatchingAndLaunchOffice(context: android.content.Context, item: DriveItem) {
        downloadFile(item) { downloadedFile ->
            _watchedItem.value = item
            _watchedFile.value = downloadedFile
            watchedFileInitialMtime = downloadedFile.lastModified()
            _autoSyncStatus.value = "🟢 مراقبة التعديل نشطة: بانتظار الحفظ في Word/Excel..."
            _autoSyncCount.value = 0

            iq.sharecoc.app.office.OfficeLauncher.openInNativeOffice(context, downloadedFile)
            startWatcherLoop()
        }
    }

    /**
     * إيقاف مراقبة التعديلات
     */
    fun stopWatching() {
        watcherJob?.cancel()
        watcherJob = null
        _watchedItem.value = null
        _watchedFile.value = null
        watchedFileInitialMtime = 0L
        _autoSyncStatus.value = ""
        _isAutoSyncing.value = false
    }

    /**
     * فحص التعديلات ومزامنتها فوراً (تُستدعى عند الرجوع للتطبيق في onResume)
     */
    fun checkAndSyncWatchedFile() {
        val item = _watchedItem.value ?: return
        val file = _watchedFile.value ?: return
        if (!file.exists()) return

        val currentMtime = file.lastModified()
        if (watchedFileInitialMtime > 0 && currentMtime > watchedFileInitialMtime && !_isAutoSyncing.value) {
            syncWatchedFileNow(item, file, currentMtime)
        }
    }

    private fun startWatcherLoop() {
        watcherJob?.cancel()
        watcherJob = viewModelScope.launch {
            while (true) {
                delay(1200)
                checkAndSyncWatchedFile()
            }
        }
    }

    /**
     * مزامنة التعديل فوراً مع Google Drive
     */
    fun syncWatchedFileNow(item: DriveItem, file: File, currentMtime: Long = file.lastModified()) {
        if (_isAutoSyncing.value) return
        viewModelScope.launch {
            _isAutoSyncing.value = true
            _autoSyncStatus.value = "⚡ تم رصد حفظ المستند! جارٍ المزامنة السحابية الفورية..."
            try {
                val ext = file.extension.lowercase()
                val mime = AppConfig.getMimeForExtension(ext)
                apiClient.updateFileContent(item.id, file, mime)
                watchedFileInitialMtime = currentMtime
                _autoSyncCount.value += 1
                _autoSyncStatus.value = "🟢 تمت المزامنة التلقائية بنجاح مع Google Drive!"
                loadFolderItems(currentFolderId)
            } catch (e: Exception) {
                Log.e(TAG, "خطأ المزامنة التلقائية: ${e.message}", e)
                _autoSyncStatus.value = "🔴 فشلت المزامنة: ${e.localizedMessage ?: e.message}"
            } finally {
                _isAutoSyncing.value = false
            }
        }
    }
}
