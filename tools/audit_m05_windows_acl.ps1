# NEURALFORGE M05 — read-only Windows filesystem ACL inventory.
# Does not create files, change access control, or install services.
[CmdletBinding()]
param(
    [string]$JournalDirectory = (Join-Path $env:LOCALAPPDATA 'NEURALFORGE\validator'),
    [string]$ServiceAccount = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-BroadSid([string]$Sid) {
    return $Sid -in @(
        'S-1-1-0',       # Everyone
        'S-1-5-11',      # Authenticated Users
        'S-1-5-32-545',  # Builtin Users
        'S-1-5-32-546',  # Guests
        'S-1-5-7',       # Anonymous Logon
        'S-1-5-2',       # Network
        'S-1-5-4'        # Interactive
    )
}
function Get-Sid([System.Security.Principal.IdentityReference]$Identity) {
    try {
        return $Identity.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch {
        return $null
    }
}
function Get-PathInventory([string]$Path) {
    $entry = [ordered]@{
        path = $Path
        exists = $false
        is_directory = $null
        reparse_point = $null
        owner = $null
        inheritance_protected = $null
        aces = @()
        findings = @()
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        $entry.findings = @('missing: cannot assess permissions')
        return [pscustomobject]$entry
    }
    $entry.exists = $true
    try {
        $item = Get-Item -LiteralPath $Path -Force
        $entry.is_directory = [bool]$item.PSIsContainer
        $entry.reparse_point = [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        if ($entry.reparse_point) { $entry.findings += 'reparse point: investigate link or junction' }
        $acl = Get-Acl -LiteralPath $Path
        $entry.owner = $acl.Owner
        $entry.inheritance_protected = [bool]$acl.AreAccessRulesProtected
        $aces = @()
        foreach ($ace in $acl.Access) {
            $sid = Get-Sid $ace.IdentityReference
            $rights = [System.Security.AccessControl.FileSystemRights]$ace.FileSystemRights
            $writeBits = [System.Security.AccessControl.FileSystemRights](
                [int][System.Security.AccessControl.FileSystemRights]::Write -bor
                [int][System.Security.AccessControl.FileSystemRights]::Modify -bor
                [int][System.Security.AccessControl.FileSystemRights]::FullControl -bor
                [int][System.Security.AccessControl.FileSystemRights]::Delete -bor
                [int][System.Security.AccessControl.FileSystemRights]::ChangePermissions -bor
                [int][System.Security.AccessControl.FileSystemRights]::TakeOwnership
            )
            $writeLike = (($rights -band $writeBits) -ne 0)
            $broad = ($null -ne $sid) -and (Test-BroadSid $sid)
            if ($broad -and $writeLike -and $ace.AccessControlType -eq 'Allow') {
                $entry.findings += "broad allow write-like ACE: $($ace.IdentityReference)"
            }
            if ($null -eq $sid) { $entry.findings += "unresolved SID: $($ace.IdentityReference)" }
            $aces += [pscustomobject]@{
                identity = [string]$ace.IdentityReference
                sid = $sid
                type = [string]$ace.AccessControlType
                rights = [string]$ace.FileSystemRights
                inherited = [bool]$ace.IsInherited
                inheritance_flags = [string]$ace.InheritanceFlags
                propagation_flags = [string]$ace.PropagationFlags
                broad_principal = [bool]$broad
                write_like = [bool]$writeLike
            }
        }
        $entry.aces = $aces
    } catch {
        # No stack trace or raw ACL printed by default.
        $entry.findings += "inspection failed: $($_.Exception.GetType().Name)"
    }
    return [pscustomobject]$entry
}

if ([string]::IsNullOrWhiteSpace($JournalDirectory)) {
    throw 'JournalDirectory is required.'
}
$directory = [System.IO.Path]::GetFullPath($JournalDirectory)
$database = Join-Path $directory 'probe_lifecycle.sqlite3'
$paths = @(
    (Split-Path -Parent $directory),
    $directory,
    $database,
    ($database + '.lock'),
    ($database + '-wal'),
    ($database + '-shm')
)
$inventory = @($paths | ForEach-Object { Get-PathInventory $_ })
$service = [ordered]@{ configured_account = $ServiceAccount; identity_found = $null; notes = @() }
if (-not [string]::IsNullOrWhiteSpace($ServiceAccount)) {
    try {
        $nt = [System.Security.Principal.NTAccount]::new($ServiceAccount)
        $service.identity_sid = $nt.Translate([System.Security.Principal.SecurityIdentifier]).Value
        $service.identity_found = $true
    } catch {
        $service.identity_found = $false
        $service.notes += 'Provided service identity could not be resolved on this computer.'
    }
} else {
    $service.notes += 'No dedicated service identity supplied; this audit cannot verify service identity isolation.'
}
$result = [ordered]@{
    schema_version = 1
    audit_type = 'neuralforge_m05_windows_acl_inventory'
    read_only = $true
    journal_directory = $directory
    current_identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    service_identity = $service
    objects = $inventory
    limitations = @(
        'ACL inventory is not an effective-access check. Deny rules, group nesting, privileges and ownership affect access.',
        'A non-broad ACE is not proof of safety. Named users, groups and inherited parent permissions need manual review.',
        'Only visible paths were inspected; missing files, parent reparse points, races and alternate access paths are not ruled out.',
        'The current per-user LOCALAPPDATA design is not a dedicated Windows service storage boundary.',
        'This script does not install a Windows service, restrict IPC, apply ACLs, or test another Windows token.',
        'Run denied-access checks using an actually separate low-privilege Windows account before security acceptance.'
    )
}
$result | ConvertTo-Json -Depth 9
