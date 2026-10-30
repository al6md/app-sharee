package iq.sharecoc.app.config

object AppConfig {
    const val APP_NAME = "Share COC"
    const val DEFAULT_ROOT_FOLDER_ID = "1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB"
    const val PERMISSIONS_CONFIG_FILENAME = ".sharecoc_permissions.json"
    const val FOLDER_MIME = "application/vnd.google-apps.folder"

    // Google OAuth2 Token Endpoint
    const val OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    const val DRIVE_API_BASE_URL = "https://www.googleapis.com/drive/v3"
    const val DRIVE_UPLOAD_BASE_URL = "https://www.googleapis.com/upload/drive/v3"

    private fun decryptBytes(bytes: ByteArray, key: Byte = 0x5C): String {
        val result = ByteArray(bytes.size)
        for (i in bytes.indices) {
            val b = (bytes[i].toInt() + 128) xor key.toInt()
            result[i] = b.toByte()
        }
        return String(result, Charsets.UTF_8)
    }

    // Default Cloud Credentials
    var clientId: String = decryptBytes(byteArrayOf(
        -18,-18,-18,-18,-18,-17,-27,-24,-18,-27,-19,-19,-15,-70,-17,-21,-20,-83,-17,-18,-72,-83,-19,-28,-77,-70,-78,-71,-70,-81,-65,-79,-21,-28,-81,-79,-67,-72,-70,-78,-65,-27,-27,-83,-73,-14,-67,-84,-84,-81,-14,-69,-77,-77,-69,-80,-71,-87,-81,-71,-82,-65,-77,-78,-88,-71,-78,-88,-14,-65,-77,-79
    ))

    var clientSecret: String = decryptBytes(byteArrayOf(
        -101,-109,-97,-113,-116,-124,-15,-27,-110,-85,-107,-65,-118,-118,-124,-15,-90,-108,-90,-81,-28,-111,-82,-124,-81,-18,-110,-28,-27,-15,-85,-118,-97,-78,-66
    ))

    var refreshToken: String = decryptBytes(byteArrayOf(
        -19,-13,-13,-20,-24,-88,-77,-110,-69,-91,-88,-80,-15,-107,-81,-117,-97,-69,-123,-107,-99,-114,-99,-99,-101,-99,-115,-113,-110,-85,-102,-15,-112,-27,-107,-82,-78,-106,-17,-78,-17,-92,-66,-86,-75,-115,-78,-90,-75,-117,-79,-105,-114,-119,-83,-75,-98,-108,-116,-76,-122,-66,-106,-71,-79,-113,-24,-99,-69,-110,-122,-86,-114,-81,-72,-18,-84,-72,-73,-21,-65,-71,-78,-103,-84,-17,-73,-67,-113,-114,-77,-112,-98,-24,-72,-86,-22,-97,-117,-75,-115,-87,-65
    ))

    var rootFolderId: String = DEFAULT_ROOT_FOLDER_ID

    // Network Timeouts & Chunks
    const val CONNECT_TIMEOUT_SEC = 30L
    const val READ_TIMEOUT_SEC = 120L
    const val CHUNK_SIZE_BYTES = 2 * 1024 * 1024 // 2MB chunk for reliable mobile uploads

    // Office MIME types
    val OFFICE_MIMES = mapOf(
        "docx" to "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc" to "application/msword",
        "xlsx" to "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls" to "application/vnd.ms-excel",
        "pptx" to "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt" to "application/vnd.ms-powerpoint",
        "pdf" to "application/pdf",
        "accdb" to "application/msaccess",
        "mdb" to "application/msaccess"
    )

    fun getMimeForExtension(ext: String): String {
        return OFFICE_MIMES[ext.lowercase()] ?: "application/octet-stream"
    }
}
