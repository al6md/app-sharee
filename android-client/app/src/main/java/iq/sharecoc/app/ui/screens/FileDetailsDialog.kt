package iq.sharecoc.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import iq.sharecoc.app.data.models.DriveItem
import iq.sharecoc.app.data.models.ItemType
import iq.sharecoc.app.ui.theme.*

@Composable
fun FileDetailsDialog(
    item: DriveItem,
    onDismiss: () -> Unit,
    onOpenOffice: () -> Unit,
    onOpenRemotePC: (String) -> Unit,
    onLockToggle: () -> Unit
) {
    var showPcIpDialog by remember { mutableStateOf(false) }
    var pcIpInput by remember { mutableStateOf("192.168.1.100") }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = PrimarySurface,
            tonalElevation = 8.dp,
            modifier = Modifier.fillMaxWidth().padding(16.dp)
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                horizontalAlignment = Alignment.Start
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "تفاصيل الملف",
                        color = AccentGold,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "إغلاق", tint = TextMuted)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // File Name & Badge
                Text(
                    text = item.name,
                    color = TextWhite,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold
                )

                Spacer(modifier = Modifier.height(6.dp))

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(text = "الحجم: ${item.formattedSize}", color = TextMuted, fontSize = 13.sp)
                    Spacer(modifier = Modifier.width(12.dp))
                    if (item.isLocked) {
                        Text(
                            text = "🔒 محجوز: ${item.lockedBy ?: "مستخدم آخر"}",
                            color = StatusYellow,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium
                        )
                    } else {
                        Text(text = "🟢 متاح للمزامنة", color = StatusGreen, fontSize = 13.sp)
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Action Buttons
                Button(
                    onClick = onOpenOffice,
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryGreen),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Icon(Icons.Default.Edit, contentDescription = null, tint = AccentGold)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = "فتح في تطبيق Office الأصلي", color = TextWhite)
                }

                Spacer(modifier = Modifier.height(10.dp))

                OutlinedButton(
                    onClick = { showPcIpDialog = true },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = AccentGold),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Icon(Icons.Default.Computer, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = "افتح على حاسوب المكتب (Remote PC)")
                }

                // خيارات خاصة بقواعد بيانات Access
                if (item.type == ItemType.ACCESS) {
                    Spacer(modifier = Modifier.height(10.dp))
                    Button(
                        onClick = onLockToggle,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (item.isLocked) StatusRed else StatusYellow
                        ),
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Icon(if (item.isLocked) Icons.Default.LockOpen else Icons.Default.Lock, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = if (item.isLocked) "فك قفل قاعدة البيانات" else "حجز قاعدة البيانات حصرياً",
                            color = Color.White
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
            }
        }
    }

    if (showPcIpDialog) {
        AlertDialog(
            onDismissRequest = { showPcIpDialog = false },
            title = { Text("فتح الملف على شاشة المكتب", color = AccentGold) },
            text = {
                Column {
                    Text("أدخل عنوان IP الخاص بجهاز الكمبيوتر في المكتب (منفذ الجسر 18290):", color = TextWhite, fontSize = 13.sp)
                    Spacer(modifier = Modifier.height(10.dp))
                    OutlinedTextField(
                        value = pcIpInput,
                        onValueChange = { pcIpInput = it },
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextWhite,
                            unfocusedTextColor = TextWhite,
                            focusedBorderColor = AccentGold
                        )
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        showPcIpDialog = false
                        onOpenRemotePC(pcIpInput)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryGreen)
                ) {
                    Text("إرسال الأمر للحاسوب", color = TextWhite)
                }
            },
            dismissButton = {
                TextButton(onClick = { showPcIpDialog = false }) {
                    Text("إلغاء", color = TextMuted)
                }
            },
            containerColor = PrimarySurface
        )
    }
}
