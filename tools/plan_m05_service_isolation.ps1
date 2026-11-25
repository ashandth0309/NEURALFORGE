#Requires -Version 5.1
<#
.SYNOPSIS
    Read-only preflight for a separate NEURALFORGE validator service identity.
.DESCRIPTION
    Never creates users, files, directories or changes ACLs.
    Inspects proposed service identity and isolated storage destination.
#>
[CmdletBinding()]
param(
    [string]$ServiceAccount = '',
    [string]$StoragePath = "$env:ProgramData\NEURALFORGE-M05-IsolationLab",
    [switch]$Json
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-Sid([string]$identity) {
    try {
        $account = New-Object System.Security.Principal.NTAccount($identity)
        return $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $null
    }
}
function Is-Protected-AdminMember([string]$identity) {
    # A nested/group-based effective admin status cannot be established here.
    # This is merely a local account group-membership signal.
    try {
        $admins = Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction Stop
        $sid = Resolve-Sid $identity
        if (-not $sid) { return $null }
        return [bool](@($admins | Where-Object { $_.SID.Value -eq $sid }).Count -gt 0)
    } catch {
        return $null
    }
}

$notes = New-Object System.Collections.Generic.List[string]
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentSid = $identity.User.Value
$serviceSid = $null
if (-not [string]::IsNullOrWhiteSpace($ServiceAccount)) {
    $serviceSid = Resolve-Sid $ServiceAccount
    if (-not $serviceSid) { $notes.Add('Service account does not resolve. Create a dedicated non-admin account separately after review.') }
    elseif ($serviceSid -eq $currentSid) { $notes.Add('REJECT: Service account is the current interactive user. This would not provide identity separation.') }
} else {
    $notes.Add('No service account selected. No effective access separation can be established.')
}

try {
    $resolvedStorage = [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($StoragePath))
} catch {
    throw 'Invalid storage path.'
}
$programDataRoot = [System.IO.Path]::GetFullPath($env:ProgramData).TrimEnd('\')
# Strictly permit immediate child of ProgramData, not existing NEURALFORGE directories.
$storageParent = [System.IO.Path]::GetDirectoryName($resolvedStorage).TrimEnd('\')
$storageLeaf = [System.IO.Path]::GetFileName($resolvedStorage.TrimEnd('\'))
$validPath = ($storageParent -ieq $programDataRoot) -and ($storageLeaf -eq 'NEURALFORGE-M05-IsolationLab')
if (-not $validPath) {
    $notes.Add('REJECT: Storage path is not the dedicated ProgramData isolation-lab directory.')
}
$exists = Test-Path -LiteralPath $resolvedStorage
if ($exists) {
    $notes.Add('Storage path already exists. Review ownership and all inherited ACLs before any provisioning.')
}
$parentAcl = $null
try {
    $acl = Get-Acl -LiteralPath $programDataRoot
    $parentAcl = @($acl.Access | ForEach-Object {
        [ordered]@{
            identity = $_.IdentityReference.Value
            rights = $_.FileSystemRights.ToString()
            access_type = $_.AccessControlType.ToString()
            inherited = $_.IsInherited
        }
    })
} catch {
    $notes.Add('Could not inspect ProgramData parent ACL. Do not provision until resolved.')
}
$adminMembership = if ($ServiceAccount) { Is-Protected-AdminMember $ServiceAccount } else { $null }
if ($adminMembership -eq $true) {
    $notes.Add('REJECT: Proposed service identity belongs directly to local Administrators.')
}
$report = [ordered]@{
    schema_version = 1
    audit_type = 'neuralforge_m05_isolation_plan'
    read_only = $true
    changes_applied = $false
    current_identity = $identity.Name
    current_sid = $currentSid
    proposed_service_account = $ServiceAccount
    proposed_service_sid = $serviceSid
    service_is_current_user = [bool]($serviceSid -and ($serviceSid -eq $currentSid))
    local_administrators_direct_membership = $adminMembership
    storage_directory = $resolvedStorage
    path_allowed_for_lab = $validPath
    storage_exists = $exists
    programdata_parent_aces = $parentAcl
    ready_for_manual_review = [bool]($validPath -and $serviceSid -and $serviceSid -ne $currentSid -and $adminMembership -eq $false -and -not $exists)
    notes = @($notes.ToArray())
    limitations = @(
        'This script does not create or harden any account, folder, database, Windows service, or IPC transport.',
        'Direct group membership is not an effective-token or nested-group evaluation.',
        'The proposed service account must be independently verified as low-privilege.',
        'A dedicated service account is not automatically authorized to access Docker Desktop.',
        'OS access denial requires testing from a separately logged-in Windows account.',
        'No inference about production security is warranted from this preflight report.'
    )
}
if ($Json) { $report | ConvertTo-Json -Depth 8 }
else { $report | Format-List }
