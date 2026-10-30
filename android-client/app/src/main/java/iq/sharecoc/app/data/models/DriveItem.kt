package iq.sharecoc.app.data.models

import com.google.gson.annotations.SerializedName

enum class ItemType {
    FOLDER,
    WORD,
    EXCEL,
    ACCESS,
    POWERPOINT,
    PDF,
    IMAGE,
    VIDEO,
    ARCHIVE,
    GENERIC_FILE
}

data class DriveItem(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String,
    @SerializedName("mimeType") val mimeType: String,
    @SerializedName("size") val sizeString: String? = null,
    @SerializedName("md5Checksum") val md5Checksum: String? = null,
    @SerializedName("modifiedTime") val modifiedTime: String? = null,
    @SerializedName("createdTime") val createdTime: String? = null,
    @SerializedName("parents") val parents: List<String>? = null,
    var localPath: String? = null,
    var isDownloading: Boolean = false,
    var downloadProgress: Float = 0f,
    var isUploading: Boolean = false,
    var uploadProgress: Float = 0f,
    var isLocked: Boolean = false,
    var lockedBy: String? = null
) {
    val isFolder: Boolean
        get() = mimeType == "application/vnd.google-apps.folder"

    val sizeBytes: Long
        get() = sizeString?.toLongOrNull() ?: 0L

    val formattedSize: String
        get() {
            if (isFolder) return "مجلد"
            val bytes = sizeBytes
            return when {
                bytes >= 1024 * 1024 * 1024 -> String.format("%.2f GB", bytes.toDouble() / (1024 * 1024 * 1024))
                bytes >= 1024 * 1024 -> String.format("%.1f MB", bytes.toDouble() / (1024 * 1024))
                bytes >= 1024 -> String.format("%.1f KB", bytes.toDouble() / 1024)
                else -> "$bytes B"
            }
        }

    val type: ItemType
        get() {
            if (isFolder) return ItemType.FOLDER
            val ext = name.substringAfterLast('.', "").lowercase()
            return when (ext) {
                "docx", "doc" -> ItemType.WORD
                "xlsx", "xls" -> ItemType.EXCEL
                "accdb", "mdb" -> ItemType.ACCESS
                "pptx", "ppt" -> ItemType.POWERPOINT
                "pdf" -> ItemType.PDF
                "jpg", "jpeg", "png", "webp", "gif" -> ItemType.IMAGE
                "mp4", "mkv", "avi", "mov" -> ItemType.VIDEO
                "zip", "rar", "7z", "tar" -> ItemType.ARCHIVE
                else -> ItemType.GENERIC_FILE
            }
        }
}
