package iq.sharecoc.app.ui.screens

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import iq.sharecoc.app.config.AppConfig
import iq.sharecoc.app.data.models.DriveItem
import iq.sharecoc.app.data.models.ItemType
import iq.sharecoc.app.office.OfficeLauncher
import iq.sharecoc.app.security.BiometricHelper
import iq.sharecoc.app.ui.theme.*
import iq.sharecoc.app.ui.viewmodel.DriveViewModel
import java.io.File
import java.io.FileOutputStream

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainExplorerScreen(viewModel: DriveViewModel) {
    val context = LocalContext.current
    val items by viewModel.items.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()
    val folderStack by viewModel.folderStack.collectAsState()
    val adminStore by viewModel.adminStore.collectAsState()
    val isAuthorized by viewModel.isDeviceAuthorized.collectAsState()
    val downloadProgress by viewModel.activeDownloadProgress.collectAsState()
    val uploadProgress by viewModel.activeUploadProgress.collectAsState()

    val watchedItem by viewModel.watchedItem.collectAsState()
    val watchedFile by viewModel.watchedFile.collectAsState()
    val autoSyncStatus by viewModel.autoSyncStatus.collectAsState()
    val autoSyncCount by viewModel.autoSyncCount.collectAsState()
    val isAutoSyncing by viewModel.isAutoSyncing.collectAsState()

    var selectedItemForDetails by remember { mutableStateOf<DriveItem?>(null) }
    var pendingFolderForPin by remember { mutableStateOf<DriveItem?>(null) }
    var showNewFolderDialog by remember { mutableStateOf(false) }
    var newFolderNameInput by remember { mutableStateOf("") }

    // لاقط اختيار ملف لرفعه من الهاتف
    val filePickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri ->
        if (uri != null) {
            val contentResolver = context.contentResolver
            val fileName = uri.lastPathSegment?.substringAfterLast('/') ?: "uploaded_doc"
            val tempFile = File(context.cacheDir, fileName)
            contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(tempFile).use { output ->
                    input.copyTo(output)
                }
            }
            val mime = contentResolver.getType(uri) ?: AppConfig.getMimeForExtension(tempFile.extension)
            viewModel.uploadFile(tempFile, mime) {
                Toast.makeText(context, "تم رفع الملف إلى Google Drive بنجاح", Toast.LENGTH_SHORT).show()
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            text = "Share COC – كربلاء المقدسة",
                            color = AccentGold,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(if (isAuthorized) StatusGreen else StatusYellow)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (isAuthorized) "🟢 سحابة Google Drive متصلة" else "🟡 الجهاز بانتظار الاعتماد",
                                color = TextMuted,
                                fontSize = 11.sp
                            )
                        }
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.loadFolderItems() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "تحديث", tint = AccentGold)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = PrimaryDark)
            )
        },
        floatingActionButton = {
            Column(horizontalAlignment = Alignment.End) {
                FloatingActionButton(
                    onClick = { showNewFolderDialog = true },
                    containerColor = PrimaryGreen,
                    contentColor = AccentGold,
                    modifier = Modifier.size(46.dp)
                ) {
                    Icon(Icons.Default.CreateNewFolder, contentDescription = "مجلد جديد")
                }
                Spacer(modifier = Modifier.height(10.dp))
                FloatingActionButton(
                    onClick = { filePickerLauncher.launch("*/*") },
                    containerColor = AccentGold,
                    contentColor = PrimaryDark
                ) {
                    Icon(Icons.Default.CloudUpload, contentDescription = "رفع ملف")
                }
            }
        },
        bottomBar = {
            watchedItem?.let { watched ->
                Surface(
                    color = Color(0xFF0B1D18),
                    tonalElevation = 8.dp,
                    shadowElevation = 12.dp,
                    shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
                    border = BorderStroke(1.dp, Color(0xFF10B981)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        if (isAutoSyncing) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = AccentGold,
                                strokeWidth = 2.5.dp
                            )
                        } else {
                            Box(
                                modifier = Modifier
                                    .size(12.dp)
                                    .clip(CircleShape)
                                    .background(StatusGreen)
                            )
                        }

                        Spacer(modifier = Modifier.width(10.dp))

                        Column(modifier = Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = "⚡ مراقبة الحفظ التلقائي",
                                    color = AccentGold,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold
                                )
                                if (autoSyncCount > 0) {
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "• $autoSyncCount مزامنة",
                                        color = StatusGreen,
                                        fontSize = 11.sp
                                    )
                                }
                            }
                            Text(
                                text = watched.name,
                                color = Color.White,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                            Text(
                                text = autoSyncStatus.ifBlank { "بانتظار الحفظ في Word/Excel..." },
                                color = TextMuted,
                                fontSize = 10.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }

                        Spacer(modifier = Modifier.width(8.dp))

                        IconButton(
                            onClick = {
                                watchedFile?.let { f ->
                                    viewModel.syncWatchedFileNow(watched, f)
                                }
                            },
                            enabled = !isAutoSyncing
                        ) {
                            Icon(
                                Icons.Default.Refresh,
                                contentDescription = "مزامنة الآن",
                                tint = AccentGold,
                                modifier = Modifier.size(20.dp)
                            )
                        }

                        IconButton(
                            onClick = { viewModel.stopWatching() }
                        ) {
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "إيقاف المراقبة",
                                tint = Color(0xFFEF4444),
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                }
            }
        },
        containerColor = PrimaryDark
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // شريط التقدم اللحظي للرفع أو التنزيل
            AnimatedVisibility(visible = downloadProgress != null || uploadProgress != null) {
                val isDl = downloadProgress != null
                val progress = downloadProgress?.second ?: uploadProgress?.second ?: 0f
                val fileName = downloadProgress?.first ?: uploadProgress?.first ?: ""

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(CardBackground)
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = if (isDl) "جارٍ تنزيل $fileName..." else "جارٍ رفع $fileName إلى Drive...",
                            color = AccentGold,
                            fontSize = 12.sp
                        )
                        Text(
                            text = "${(progress * 100).toInt()}%",
                            color = TextWhite,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                        color = AccentGold,
                        trackColor = PrimarySurface
                    )
                }
            }

            // شريط التنقل ومسار المجلدات (Breadcrumbs)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(PrimarySurface)
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                folderStack.forEachIndexed { index, crumb ->
                    val isLast = index == folderStack.size - 1
                    Text(
                        text = crumb.name,
                        color = if (isLast) AccentGold else TextMuted,
                        fontWeight = if (isLast) FontWeight.Bold else FontWeight.Normal,
                        fontSize = 13.sp,
                        modifier = Modifier
                            .clickable(enabled = !isLast) {
                                viewModel.navigateToBreadcrumbIndex(index)
                            }
                            .padding(horizontal = 4.dp)
                    )
                    if (!isLast) {
                        Icon(
                            imageVector = Icons.Default.ChevronLeft,
                            contentDescription = null,
                            tint = TextMuted,
                            modifier = Modifier.size(16.dp)
                        )
                    }
                }
            }

            // رسائل التنبيه أو الخطأ
            if (errorMessage != null) {
                Surface(
                    color = StatusRed.copy(alpha = 0.2f),
                    modifier = Modifier.fillMaxWidth().padding(12.dp),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Warning, contentDescription = null, tint = StatusRed)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(text = errorMessage ?: "", color = TextWhite, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        IconButton(onClick = { viewModel.clearError() }) {
                            Icon(Icons.Default.Close, contentDescription = null, tint = TextMuted)
                        }
                    }
                }
            }

            // قائمة الملفات
            Box(modifier = Modifier.fillMaxSize()) {
                if (isLoading && items.isEmpty()) {
                    CircularProgressIndicator(
                        color = AccentGold,
                        modifier = Modifier.align(Alignment.Center)
                    )
                } else if (items.isEmpty()) {
                    Column(
                        modifier = Modifier.align(Alignment.Center),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            Icons.Default.FolderOpen,
                            contentDescription = null,
                            tint = TextMuted,
                            modifier = Modifier.size(54.dp)
                        )
                        Spacer(modifier = Modifier.height(10.dp))
                        Text(text = "لا توجد ملفات في هذا المجلد السحابي", color = TextMuted, fontSize = 14.sp)
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp)
                    ) {
                        items(items, key = { it.id }) { item ->
                            DriveItemRow(
                                item = item,
                                onItemClick = {
                                    if (item.isFolder) {
                                        // التحقق من كود الـ PIN إن كان القسم محمياً
                                        val deptConfig = adminStore.departments[item.name]
                                        if (deptConfig?.pinCode?.isNotBlank() == true) {
                                            pendingFolderForPin = item
                                        } else {
                                            viewModel.navigateToFolder(item.id, item.name)
                                        }
                                    } else {
                                        selectedItemForDetails = item
                                    }
                                },
                                onActionClick = {
                                    if (!item.isFolder) {
                                        selectedItemForDetails = item
                                    }
                                }
                            )
                            Spacer(modifier = Modifier.height(6.dp))
                        }
                    }
                }
            }
        }
    }

    // نافذة تفاصيل الملف
    selectedItemForDetails?.let { item ->
        FileDetailsDialog(
            item = item,
            onDismiss = { selectedItemForDetails = null },
            onOpenOffice = {
                selectedItemForDetails = null
                viewModel.startWatchingAndLaunchOffice(context, item)
            },
            onOpenRemotePC = { pcIp ->
                selectedItemForDetails = null
                viewModel.launchOnRemoteOfficePC(pcIp, item.name) { success ->
                    val msg = if (success) "تم إرسال أمر الفتح لحاسوب المكتب بنجاح!" else "تعذر الوصول لحاسوب المكتب، تأكد من الاتصال بالواي فاي"
                    Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
                }
            },
            onLockToggle = {
                selectedItemForDetails = null
                if (item.isLocked) {
                    viewModel.unlockAccessDatabase(item)
                } else {
                    viewModel.lockAccessDatabase(item)
                }
            }
        )
    }

    // نافذة إدخال رمز PIN أو البصمة للقسم المحمي
    pendingFolderForPin?.let { folder ->
        val deptConfig = adminStore.departments[folder.name]
        val expectedPin = deptConfig?.pinCode ?: ""

        PinVerificationDialog(
            departmentName = folder.name,
            onDismiss = { pendingFolderForPin = null },
            onVerifyPin = { enteredPin ->
                if (enteredPin == expectedPin) {
                    val target = pendingFolderForPin
                    pendingFolderForPin = null
                    target?.let { viewModel.navigateToFolder(it.id, it.name) }
                } else {
                    Toast.makeText(context, "رمز المرور غير صحيح!", Toast.LENGTH_SHORT).show()
                }
            },
            onBiometricClick = {
                val act = context as? FragmentActivity
                if (act != null && BiometricHelper.isBiometricAvailable(context)) {
                    BiometricHelper.promptBiometric(
                        activity = act,
                        title = "تأكيد الوصول إلى قسم ${folder.name}",
                        onSuccess = {
                            val target = pendingFolderForPin
                            pendingFolderForPin = null
                            target?.let { viewModel.navigateToFolder(it.id, it.name) }
                        },
                        onError = { err ->
                            Toast.makeText(context, err, Toast.LENGTH_SHORT).show()
                        }
                    )
                } else {
                    Toast.makeText(context, "البصمة غير متوفرة أو غير مفعّلة في جهازك", Toast.LENGTH_SHORT).show()
                }
            }
        )
    }

    // نافذة إنشاء مجلد جديد
    if (showNewFolderDialog) {
        AlertDialog(
            onDismissRequest = { showNewFolderDialog = false },
            title = { Text("إنشاء مجلد جديد في Google Drive", color = AccentGold) },
            text = {
                OutlinedTextField(
                    value = newFolderNameInput,
                    onValueChange = { newFolderNameInput = it },
                    label = { Text("اسم المجلد") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = TextWhite,
                        unfocusedTextColor = TextWhite,
                        focusedBorderColor = AccentGold
                    )
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (newFolderNameInput.isNotBlank()) {
                            viewModel.createFolder(newFolderNameInput.trim())
                            newFolderNameInput = ""
                            showNewFolderDialog = false
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryGreen)
                ) {
                    Text("إنشاء", color = TextWhite)
                }
            },
            dismissButton = {
                TextButton(onClick = { showNewFolderDialog = false }) {
                    Text("إلغاء", color = TextMuted)
                }
            },
            containerColor = PrimarySurface
        )
    }
}

@Composable
fun DriveItemRow(
    item: DriveItem,
    onItemClick: () -> Unit,
    onActionClick: () -> Unit
) {
    Surface(
        color = CardBackground,
        shape = RoundedCornerShape(12.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onItemClick)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Icon
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(getItemIconBg(item.type)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = getItemIcon(item.type),
                    contentDescription = null,
                    tint = getItemIconTint(item.type),
                    modifier = Modifier.size(24.dp)
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            // Details
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.name,
                    color = TextWhite,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(3.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(text = item.formattedSize, color = TextMuted, fontSize = 11.sp)
                    if (item.isLocked) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "🔒 محجوز: ${item.lockedBy ?: ""}",
                            color = StatusYellow,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            // Quick Action or Chevron
            IconButton(onClick = onActionClick) {
                Icon(
                    imageVector = if (item.isFolder) Icons.Default.ChevronLeft else Icons.Default.MoreVert,
                    contentDescription = null,
                    tint = TextMuted
                )
            }
        }
    }
}

fun getItemIcon(type: ItemType): ImageVector {
    return when (type) {
        ItemType.FOLDER -> Icons.Default.Folder
        ItemType.WORD -> Icons.Default.Description
        ItemType.EXCEL -> Icons.Default.TableChart
        ItemType.ACCESS -> Icons.Default.Storage
        ItemType.POWERPOINT -> Icons.Default.Slideshow
        ItemType.PDF -> Icons.Default.PictureAsPdf
        ItemType.IMAGE -> Icons.Default.Image
        ItemType.VIDEO -> Icons.Default.Movie
        ItemType.ARCHIVE -> Icons.Default.Archive
        ItemType.GENERIC_FILE -> Icons.Default.InsertDriveFile
    }
}

fun getItemIconBg(type: ItemType): Color {
    return when (type) {
        ItemType.FOLDER -> AccentGold.copy(alpha = 0.15f)
        ItemType.WORD -> Color(0xFF2B579A).copy(alpha = 0.2f)
        ItemType.EXCEL -> Color(0xFF217346).copy(alpha = 0.2f)
        ItemType.ACCESS -> Color(0xFFA4373A).copy(alpha = 0.2f)
        ItemType.POWERPOINT -> Color(0xFFD24726).copy(alpha = 0.2f)
        ItemType.PDF -> Color(0xFFE5252A).copy(alpha = 0.2f)
        else -> Color.Gray.copy(alpha = 0.15f)
    }
}

fun getItemIconTint(type: ItemType): Color {
    return when (type) {
        ItemType.FOLDER -> AccentGold
        ItemType.WORD -> Color(0xFF6BA3F5)
        ItemType.EXCEL -> Color(0xFF48C774)
        ItemType.ACCESS -> Color(0xFFF16D75)
        ItemType.POWERPOINT -> Color(0xFFFF8555)
        ItemType.PDF -> Color(0xFFFF5252)
        else -> TextWhite
    }
}
