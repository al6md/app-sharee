package iq.sharecoc.app.data.models

import com.google.gson.annotations.SerializedName

data class DepartmentPermissionConfig(
    @SerializedName("departmentName") val departmentName: String,
    @SerializedName("canView") val canView: Boolean = true,
    @SerializedName("canDownload") val canDownload: Boolean = true,
    @SerializedName("canUpload") val canUpload: Boolean = true,
    @SerializedName("canCreateFolder") val canCreateFolder: Boolean = true,
    @SerializedName("canEdit") val canEdit: Boolean = true,
    @SerializedName("canRename") val canRename: Boolean = true,
    @SerializedName("canMove") val canMove: Boolean = true,
    @SerializedName("canDelete") val canDelete: Boolean = false,
    @SerializedName("canPermanentDelete") val canPermanentDelete: Boolean = false,
    @SerializedName("pinCode") val pinCode: String? = null,
    @SerializedName("updatedAt") val updatedAt: String? = null
)

data class AuthorizedDeviceConfig(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String,
    @SerializedName("user") val user: String,
    @SerializedName("os") val os: String,
    @SerializedName("machineGuid") val machineGuid: String,
    @SerializedName("isAuthorized") var isAuthorized: Boolean = true,
    @SerializedName("lastSeen") var lastSeen: String = "متصل الآن",
    @SerializedName("status") var status: String? = "متصل الآن"
)

data class AdminCredentialsConfig(
    @SerializedName("username") val username: String = "admin",
    @SerializedName("password") val password: String = "admin1234",
    @SerializedName("updatedAt") val updatedAt: String = ""
)

data class CloudAdminStore(
    @SerializedName("version") val version: Int = 1,
    @SerializedName("updatedAt") val updatedAt: String = "",
    @SerializedName("adminCredentials") val adminCredentials: AdminCredentialsConfig = AdminCredentialsConfig(),
    @SerializedName("devices") val devices: MutableList<AuthorizedDeviceConfig> = mutableListOf(),
    @SerializedName("departments") val departments: MutableMap<String, DepartmentPermissionConfig> = mutableMapOf()
)
