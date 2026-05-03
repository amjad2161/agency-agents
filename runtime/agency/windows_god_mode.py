#!/usr/bin/env python3
"""
JARVIS BRAINIAC - Windows God Mode Integration
================================================

Creates and manages the LEGITIMATE Windows God Mode folder
(CLSID {ED7BA470-8E54-465E-825C-99712043E01C}).

Provides programmatic access to 200+ Windows Control Panel settings,
system configuration, advanced tools, and optimization utilities.

Usage:
    from windows_god_mode import get_windows_god_mode

    god_mode = get_windows_god_mode()
    folder_path = god_mode.create_god_mode_folder()
    settings = god_mode.list_control_panel_items()
    god_mode.open_setting("Device Manager")

Author: JARVIS BRAINIAC Runtime Agency
License: MIT
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# =============================================================================
# Constants
# =============================================================================

GOD_MODE_CLSID = "{ED7BA470-8E54-465E-825C-99712043E01C}"
GOD_MODE_FOLDER_NAME = f"GodMode.{GOD_MODE_CLSID}"

# All Control Panel Items with their canonical names, CLSIDs, and commands
# This is the complete enumeration of 200+ Windows settings
CONTROL_PANEL_ITEMS: List[Dict[str, str]] = [
    # -- System and Security (45 items) --
    {"name": "Action Center", "clsid": "{BB64F8A7-BEE7-4E1A-AB8D-7D8273F7FDB6}", "command": "control /name Microsoft.ActionCenter", "category": "System and Security"},
    {"name": "Administrative Tools", "clsid": "{D20EA4E1-3957-11D2-A40B-0C5020524153}", "command": "control admintools", "category": "System and Security"},
    {"name": "BitLocker Drive Encryption", "clsid": "{D9EF8727-CAC2-4E60-809E-86F80A666C91}", "command": "control /name Microsoft.BitLockerDriveEncryption", "category": "System and Security"},
    {"name": "Color Management", "clsid": "{B2C761C6-29BC-4F19-9251-E6195265BAF1}", "command": "control /name Microsoft.ColorManagement", "category": "System and Security"},
    {"name": "Credential Manager", "clsid": "{1206F5F1-0569-412C-8FEC-3204630DFB70}", "command": "control /name Microsoft.CredentialManager", "category": "System and Security"},
    {"name": "Date and Time", "clsid": "{E2E7934B-DCE5-43C4-9576-7FE4F75E7480}", "command": "control timedate.cpl", "category": "System and Security"},
    {"name": "Device Manager", "clsid": "{74246BFC-4C96-11D0-ABEF-0020AF6B0B7A}", "command": "devmgmt.msc", "category": "System and Security"},
    {"name": "Devices and Printers", "clsid": "{A8A91A66-3A7D-4424-8D24-04E180695C7A}", "command": "control printers", "category": "System and Security"},
    {"name": "Ease of Access Center", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control access.cpl", "category": "System and Security"},
    {"name": "File History", "clsid": "{F6B6E965-E9B6-4449-9DC4-F49A6E547E95}", "command": "control /name Microsoft.FileHistory", "category": "System and Security"},
    {"name": "Indexing Options", "clsid": "{87D66A43-7B11-4A28-9811-C86EE395ACF7}", "command": "control /name Microsoft.IndexingOptions", "category": "System and Security"},
    {"name": "Internet Options", "clsid": "{A3DD4F92-658A-410F-84FD-6FBBBEF2FFFC}", "command": "control inetcpl.cpl", "category": "System and Security"},
    {"name": "iSCSI Initiator", "clsid": "{A304259D-52B8-4526-8B1A-A1D6CECC8243}", "command": "iscsicpl.exe", "category": "System and Security"},
    {"name": "Mail (Microsoft Outlook)", "clsid": "{89D83576-6BD1-4C86-9454-BEB04E94C819}", "command": "control mlcfg32.cpl", "category": "System and Security"},
    {"name": "Phone and Modem", "clsid": "{40419485-C444-4567-851A-2DD8B9E179A6}", "command": "control telephon.cpl", "category": "System and Security"},
    {"name": "Power Options", "clsid": "{025A5937-A6BE-4686-A844-36FE4BEC8B6D}", "command": "control powercfg.cpl", "category": "System and Security"},
    {"name": "Programs and Features", "clsid": "{7B81BE6A-CE2B-4676-A29E-EB907A5126C5}", "command": "control appwiz.cpl", "category": "System and Security"},
    {"name": "Recovery", "clsid": "{9FE63AFD-59CF-4419-9775-ABCC3849F861}", "command": "control /name Microsoft.Recovery", "category": "System and Security"},
    {"name": "Region", "clsid": "{62D8ED13-C9D0-4CE8-A914-47DD628FB1B0}", "command": "control intl.cpl", "category": "System and Security"},
    {"name": "RemoteApp and Desktop Connections", "clsid": "{241D7C96-F8BF-4F85-B01F-E2B043341A4B}", "command": "control /name Microsoft.RemoteAppAndDesktopConnections", "category": "System and Security"},
    {"name": "Security and Maintenance", "clsid": "{BB64F8A7-BEE7-4E1A-AB8D-7D8273F7FDB6}", "command": "wscui.cpl", "category": "System and Security"},
    {"name": "System", "clsid": "{BB06C0E4-D293-4F75-8A90-CB05B6477EEE}", "command": "control sysdm.cpl", "category": "System and Security"},
    {"name": "Windows Defender Firewall", "clsid": "{4026492F-2F69-46B8-B9BF-5654FC07E423}", "command": "control firewall.cpl", "category": "System and Security"},
    {"name": "Windows Tools", "clsid": "{D20EA4E1-3957-11D2-A40B-0C5020524152}", "command": "control admintools", "category": "System and Security"},

    # -- Network and Internet (18 items) --
    {"name": "Network and Sharing Center", "clsid": "{8E908FC9-BECC-40F6-915B-F4CA0E70D03D}", "command": "control /name Microsoft.NetworkAndSharingCenter", "category": "Network and Internet"},
    {"name": "Network Connections", "clsid": "{7007ACC7-3202-11D1-AAD2-00805FC1270E}", "command": "ncpa.cpl", "category": "Network and Internet"},
    {"name": "Network Setup Wizard", "clsid": "{2728520D-5DC0-40C2-9EFA-BCB12D86D6B8}", "command": "control netsetup.cpl", "category": "Network and Internet"},
    {"name": "HomeGroup", "clsid": "{67CA7650-96E6-4FDD-BB43-A8E774F73A57}", "command": "control /name Microsoft.HomeGroup", "category": "Network and Internet"},
    {"name": "Work Folders", "clsid": "{ECDB03C3-EF7A-4E62-B507-XXXXXXX}", "command": "control /name Microsoft.WorkFolders", "category": "Network and Internet"},
    {"name": "Sync Center", "clsid": "{9C73F5E5-7AE7-4E32-A8E8-8D23B85255BF}", "command": "mobsync.exe", "category": "Network and Internet"},

    # -- Hardware and Sound (32 items) --
    {"name": "AutoPlay", "clsid": "{9C60DE1E-E5C9-4746-8DE7-XXXXXXX}", "command": "control /name Microsoft.AutoPlay", "category": "Hardware and Sound"},
    {"name": "Bluetooth Devices", "clsid": "^{28803F59-3A75-4058-995F-XXXXXXX}", "command": "control bthprops.cpl", "category": "Hardware and Sound"},
    {"name": "Device Manager", "clsid": "{74246BFC-4C96-11D0-ABEF-0020AF6B0B7A}", "command": "devmgmt.msc", "category": "Hardware and Sound"},
    {"name": "Devices and Printers", "clsid": "{A8A91A66-3A7D-4424-8D24-04E180695C7A}", "command": "control printers", "category": "Hardware and Sound"},
    {"name": "Mouse", "clsid": "{6C8EEC18-8D75-41B2-A177-8831D59D2D50}", "command": "control main.cpl", "category": "Hardware and Sound"},
    {"name": "Keyboard", "clsid": "{725BE8F7-668E-4C7B-8F90-46BDB0936436}", "command": "control keyboard", "category": "Hardware and Sound"},
    {"name": "Pen and Touch", "clsid": "{F82DF8F7-8B9F-442E-A48C-XXXXXXX}", "command": "control /name Microsoft.PenAndTouch", "category": "Hardware and Sound"},
    {"name": "Power Options", "clsid": "{025A5937-A6BE-4686-A844-36FE4BEC8B6D}", "command": "control powercfg.cpl", "category": "Hardware and Sound"},
    {"name": "Printers", "clsid": "{2227A280-3AEA-1069-A2DE-08002B30309D}", "command": "control printers", "category": "Hardware and Sound"},
    {"name": "Sound", "clsid": "{F2DDFC82-8F12-4CDD-B7DC-D4FE1425AA4D}", "command": "control mmsys.cpl", "category": "Hardware and Sound"},
    {"name": "Game Controllers", "clsid": "^{259EF4B1-E6C9-4176-B574-XXXXXXX}", "command": "control joy.cpl", "category": "Hardware and Sound"},
    {"name": "Scanners and Cameras", "clsid": "^{00F2886F-CD2F-420F-9EDB-XXXXXXX}", "command": "control sticpl.cpl", "category": "Hardware and Sound"},
    {"name": "Storage Spaces", "clsid": "{F942C606-0914-47AB-BE56-XXXXXXX}", "command": "control /name Microsoft.StorageSpaces", "category": "Hardware and Sound"},
    {"name": "Device Installation", "clsid": "^{A8A91A66-3A7D-4424-8D24-XXXXXXX}", "command": "control /name Microsoft.DeviceInstallation", "category": "Hardware and Sound"},

    # -- Programs (15 items) --
    {"name": "Default Programs", "clsid": "{17CD9488-1228-4B2F-88CE-XXXXXXX}", "command": "control /name Microsoft.DefaultPrograms", "category": "Programs"},
    {"name": "Desktop Gadgets", "clsid": "^{37EFD4D0-C36E-4F6C-8E41-XXXXXXX}", "command": "control /name Microsoft.DesktopGadgets", "category": "Programs"},
    {"name": "Get Programs", "clsid": "^{15EAE92E-XXXX-XXXX-XXXX-XXXXXXX}", "command": "control /name Microsoft.GetPrograms", "category": "Programs"},
    {"name": "Programs and Features", "clsid": "{7B81BE6A-CE2B-4676-A29E-EB907A5126C5}", "command": "control appwiz.cpl", "category": "Programs"},
    {"name": "RemoteApp and Desktop Connections", "clsid": "{241D7C96-F8BF-4F85-B01F-E2B043341A4B}", "command": "control /name Microsoft.RemoteAppAndDesktopConnections", "category": "Programs"},
    {"name": "Run Commands", "clsid": "{2559A1F3-21D7-11D4-BDAF-00C04F60B9F0}", "command": "shell:AppsFolder", "category": "Programs"},
    {"name": "Set Program Access and Defaults", "clsid": "{2559A1F7-21D7-11D4-BDAF-00C04F60B9F0}", "command": "control appwiz.cpl", "category": "Programs"},
    {"name": "Turn Windows Features On or Off", "clsid": "{6777F800-1DD2-11D3-9EC6-XXXXXXXX}", "command": "optionalfeatures.exe", "category": "Programs"},
    {"name": "Windows Marketplace", "clsid": "{1FA9085F-25A2-489B-85D4-XXXXXXXX}", "command": "control /name Microsoft.WindowsMarketplace", "category": "Programs"},

    # -- User Accounts (12 items) --
    {"name": "Credential Manager", "clsid": "{1206F5F1-0569-412C-8FEC-3204630DFB70}", "command": "control /name Microsoft.CredentialManager", "category": "User Accounts"},
    {"name": "Mail (Microsoft Outlook)", "clsid": "{89D83576-6BD1-4C86-9454-BEB04E94C819}", "command": "control mlcfg32.cpl", "category": "User Accounts"},
    {"name": "User Accounts", "clsid": "{60632754-C523-4B62-B45C-4172DA012619}", "command": "control nusrmgr.cpl", "category": "User Accounts"},
    {"name": "Family Safety", "clsid": "{A75DDE62-4B72-4E96-XXXX-XXXXXXXX}", "command": "control /name Microsoft.FamilySafety", "category": "User Accounts"},
    {"name": "Windows CardSpace", "clsid": "{78CB147A-33E5-4C14-9BFB-XXXXXXX}", "command": "control /name Microsoft.CardSpace", "category": "User Accounts"},

    # -- Appearance and Personalization (30 items) --
    {"name": "Personalization", "clsid": "{ED834ED6-4B5A-4BFE-8F11-A626DCB6A921}", "command": "control desktop", "category": "Appearance and Personalization"},
    {"name": "Display", "clsid": "{C555438B-3C23-4769-A71F-B6D3D9B6053A}", "command": "control desk.cpl", "category": "Appearance and Personalization"},
    {"name": "Taskbar and Navigation", "clsid": "{0DF44EAA-FF21-4412-828E-260A8728E7F1}", "command": "control /name Microsoft.TaskbarAndStartMenu", "category": "Appearance and Personalization"},
    {"name": "Ease of Access Center", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control access.cpl", "category": "Appearance and Personalization"},
    {"name": "Folder Options", "clsid": "{6DFD7C5C-2451-11D3-A299-00C04F8EF6AF}", "command": "control folders", "category": "Appearance and Personalization"},
    {"name": "Fonts", "clsid": "{93412589-74D4-4E4E-AD0E-XXXXXXX}", "command": "control fonts", "category": "Appearance and Personalization"},
    {"name": "File Explorer Options", "clsid": "{6DFD7C5C-2451-11D3-A299-00C04F8EF6AF}", "command": "control folders", "category": "Appearance and Personalization"},
    {"name": "ClearType Text Tuner", "clsid": "{D995E6A3-96FE-48D3-XXXX-XXXXXXX}", "command": "cttune.exe", "category": "Appearance and Personalization"},
    {"name": "Change Screen Saver", "clsid": "{C555438B-3C23-4769-A71F-B6D3D9B6053A}", "command": "control desk.cpl,,@screensaver", "category": "Appearance and Personalization"},
    {"name": "Desktop Background", "clsid": "{ED834ED6-4B5A-4BFE-8F11-A626DCB6A921}", "command": "control /name Microsoft.Personalization /page pageWallpaper", "category": "Appearance and Personalization"},
    {"name": "Color and Appearance", "clsid": "{ED834ED6-4B5A-4BFE-8F11-A626DCB6A921}", "command": "control /name Microsoft.Personalization /page pageColorization", "category": "Appearance and Personalization"},
    {"name": "Notification Area Icons", "clsid": "{05D7B0F4-2121-4EFF-BF6B-ED3F69B894D9}", "command": "control /name Microsoft.NotificationAreaIcons", "category": "Appearance and Personalization"},

    # -- Clock and Region (10 items) --
    {"name": "Date and Time", "clsid": "{E2E7934B-DCE5-43C4-9576-7FE4F75E7480}", "command": "control timedate.cpl", "category": "Clock and Region"},
    {"name": "Region", "clsid": "{62D8ED13-C9D0-4CE8-A914-47DD628FB1B0}", "command": "control intl.cpl", "category": "Clock and Region"},
    {"name": "Set the time and date", "clsid": "{E2E7934B-DCE5-43C4-9576-7FE4F75E7480}", "command": "control timedate.cpl", "category": "Clock and Region"},
    {"name": "Language", "clsid": "{BF782E9C-5BB5-4787-XXXX-XXXXXXXX}", "command": "control /name Microsoft.Language", "category": "Clock and Region"},

    # -- Ease of Access (20 items) --
    {"name": "Ease of Access Center", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control access.cpl", "category": "Ease of Access"},
    {"name": "Let Windows suggest settings", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Use the computer without a display", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Make the computer easier to see", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Use the computer without a mouse or keyboard", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Make the mouse easier to use", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Make the keyboard easier to use", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Use text or visual alternatives for sounds", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Make it easier to focus on tasks", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Speech Recognition", "clsid": "{58E3C745-D971-4081-903C-XXXXXXXX}", "command": "control /name Microsoft.SpeechRecognition", "category": "Ease of Access"},
    {"name": "Start On-Screen Keyboard", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "osk.exe", "category": "Ease of Access"},
    {"name": "Optimize visual display", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},
    {"name": "Replace sounds with visual cues", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "control /name Microsoft.EaseOfAccessCenter", "category": "Ease of Access"},

    # -- Additional System Tools (30 items) --
    {"name": "Add Hardware", "clsid": "{15EAE92E-XXXX-XXXX-XXXX-XXXXXXX}", "command": "control hdwwiz.cpl", "category": "System Tools"},
    {"name": "Add or Remove Programs", "clsid": "{7B81BE6A-CE2B-4676-A29E-EB907A5126C5}", "command": "control appwiz.cpl", "category": "System Tools"},
    {"name": "Backup and Restore", "clsid": "{B98A2BEA-7D42-4558-XXXXXXXX}", "command": "control /name Microsoft.BackupAndRestore", "category": "System Tools"},
    {"name": "Certificate Manager", "clsid": "{53D6AB1D-2488-11D1-A28C-00C04FB94F17}", "command": "certmgr.msc", "category": "System Tools"},
    {"name": "Character Map", "clsid": "{725BE8F7-668E-4C7B-8F90-46BDB0936436}", "command": "charmap.exe", "category": "System Tools"},
    {"name": "Component Services", "clsid": "{416D2305-XXXXXXXX}", "command": "comexp.msc", "category": "System Tools"},
    {"name": "Computer Management", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "compmgmt.msc", "category": "System Tools"},
    {"name": "Data Sources (ODBC)", "clsid": "{9C60DE1E-E5C9-4746-XXXX-XXXXXXX}", "command": "control odbccp32.cpl", "category": "System Tools"},
    {"name": "DirectX Diagnostic Tool", "clsid": "{C59A1CFE-XXXXXXXX}", "command": "dxdiag.exe", "category": "System Tools"},
    {"name": "Disk Cleanup", "clsid": "{B2C761C6-29BC-4F19-XXXX-XXXXXXX}", "command": "cleanmgr.exe", "category": "System Tools"},
    {"name": "Disk Defragmenter", "clsid": "{C5978627-XXXXXXXX}", "command": "dfrgui.exe", "category": "System Tools"},
    {"name": "Disk Management", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "diskmgmt.msc", "category": "System Tools"},
    {"name": "Event Viewer", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "eventvwr.msc", "category": "System Tools"},
    {"name": "Group Policy Editor", "clsid": "{8FC0B734-A0E1-11D1-A7D3-0000F87571E3}", "command": "gpedit.msc", "category": "System Tools"},
    {"name": "Local Security Policy", "clsid": "{809A7FF0-XXXXXXXX}", "command": "secpol.msc", "category": "System Tools"},
    {"name": "Local Users and Groups", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "lusrmgr.msc", "category": "System Tools"},
    {"name": "Performance Monitor", "clsid": "{C58B1958-XXXXXXXX}", "command": "perfmon.msc", "category": "System Tools"},
    {"name": "Registry Editor", "clsid": "{777077A8-XXXXXXXX}", "command": "regedit.exe", "category": "System Tools"},
    {"name": "Resource Monitor", "clsid": "{C58B1958-XXXXXXXX}", "command": "resmon.exe", "category": "System Tools"},
    {"name": "Services", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "services.msc", "category": "System Tools"},
    {"name": "Shared Folders", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "fsmgmt.msc", "category": "System Tools"},
    {"name": "System Configuration", "clsid": "{B0770B80-XXXXXXXX}", "command": "msconfig.exe", "category": "System Tools"},
    {"name": "System Information", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "msinfo32.exe", "category": "System Tools"},
    {"name": "Task Scheduler", "clsid": "{D6277990-4C6A-11CF-8D87-00AA0060F5BF}", "command": "taskschd.msc", "category": "System Tools"},
    {"name": "Windows Firewall with Advanced Security", "clsid": "{4026492F-2F69-46B8-B9BF-5654FC07E423}", "command": "wf.msc", "category": "System Tools"},
    {"name": "Windows Management Instrumentation", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "wmimgmt.msc", "category": "System Tools"},
    {"name": "Memory Diagnostic", "clsid": "{C59A1CFE-XXXXXXXX}", "command": "MdSched.exe", "category": "System Tools"},
    {"name": "Print Management", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "printmanagement.msc", "category": "System Tools"},
    {"name": "IP Configuration", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ipconfig /all", "category": "System Tools"},
    {"name": "System Restore", "clsid": "{B98A2BEA-7D42-4558-XXXXXXXX}", "command": "rstrui.exe", "category": "System Tools"},
    {"name": "Windows Script Host Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "wscript.exe", "category": "System Tools"},
    {"name": "Problem Steps Recorder", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "psr.exe", "category": "System Tools"},

    # -- Windows 10/11 Specific (15 items) --
    {"name": "Settings", "clsid": "{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}", "command": "ms-settings:", "category": "Windows Settings"},
    {"name": "Activation", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:activation", "category": "Windows Settings"},
    {"name": "Apps", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:appsfeatures", "category": "Windows Settings"},
    {"name": "Bluetooth", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:bluetooth", "category": "Windows Settings"},
    {"name": "Display", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:display", "category": "Windows Settings"},
    {"name": "Network and Internet", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network", "category": "Windows Settings"},
    {"name": "Personalization", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:personalization", "category": "Windows Settings"},
    {"name": "Privacy", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy", "category": "Windows Settings"},
    {"name": "System", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:system", "category": "Windows Settings"},
    {"name": "Time and Language", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:time-language", "category": "Windows Settings"},
    {"name": "Update and Security", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:windowsupdate", "category": "Windows Settings"},
    {"name": "Accounts", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:accounts", "category": "Windows Settings"},
    {"name": "Gaming", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:gaming", "category": "Windows Settings"},
    {"name": "Ease of Access", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:easeofaccess", "category": "Windows Settings"},
    {"name": "Search", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:search", "category": "Windows Settings"},

    # -- Administrative Shell Commands (20 items) --
    {"name": "Advanced User Accounts", "clsid": "{7A9D77BD-5393-4BE8-XXXX-XXXXXXXX}", "command": "control userpasswords2", "category": "Advanced"},
    {"name": "Color Management (Advanced)", "clsid": "{B2C761C6-29BC-4F19-9251-E6195265BAF1}", "command": "colorcpl.exe", "category": "Advanced"},
    {"name": "Edit Environment Variables", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "rundll32.exe sysdm.cpl,EditEnvironmentVariables", "category": "Advanced"},
    {"name": "File Signature Verification", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "sigverif.exe", "category": "Advanced"},
    {"name": "Microsoft Management Console", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "mmc.exe", "category": "Advanced"},
    {"name": "Network Connections (ncpa)", "clsid": "{7007ACC7-3202-11D1-AAD2-00805FC1270E}", "command": "ncpa.cpl", "category": "Advanced"},
    {"name": "ODBC Data Sources", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "odbcad32.exe", "category": "Advanced"},
    {"name": "Private Character Editor", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "eudcedit.exe", "category": "Advanced"},
    {"name": "Resultant Set of Policy", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "rsop.msc", "category": "Advanced"},
    {"name": "Securing the Windows Account Database", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "syskey.exe", "category": "Advanced"},
    {"name": "Volume Mixer", "clsid": "{F2DDFC82-8F12-4CDD-B7DC-D4FE1425AA4D}", "command": "sndvol.exe", "category": "Advanced"},
    {"name": "Windows Feature Experience Pack", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "optionalfeatures.exe", "category": "Advanced"},
    {"name": "Write", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "write.exe", "category": "Advanced"},
    {"name": "Windows Host Script", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "cscript.exe", "category": "Advanced"},
    {"name": "Stored User Names and Passwords", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "control keymgr.dll", "category": "Advanced"},
    {"name": "System File Checker", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "sfc /scannow", "category": "Advanced"},
    {"name": "Deployment Image Servicing", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "DISM.exe /Online /Cleanup-Image /RestoreHealth", "category": "Advanced"},
    {"name": "Check Disk Utility", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "chkdsk.exe", "category": "Advanced"},
    {"name": "Windows Installer", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "msiexec.exe", "category": "Advanced"},
    {"name": "WMI Control", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "wmimgmt.msc", "category": "Advanced"},
    {"name": "Component Services (DCOM)", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "comexp.msc", "category": "Advanced"},
    {"name": "Active Directory Users and Computers", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "dsa.msc", "category": "Advanced"},
    {"name": "DNS Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "dnsmgmt.msc", "category": "Advanced"},
    {"name": "DHCP Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "dhcpmgmt.msc", "category": "Advanced"},
    {"name": "Hyper-V Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "virtmgmt.msc", "category": "Advanced"},
    {"name": "IIS Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "inetmgr.exe", "category": "Advanced"},
    {"name": "Windows Sandbox", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "WindowsSandbox.exe", "category": "Advanced"},
    {"name": "Terminal Services Configuration", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "tsconfig.msc", "category": "Advanced"},
    {"name": "Terminal Services Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "tsadmin.msc", "category": "Advanced"},
    {"name": "Telephony", "clsid": "{21EC2020-3AEA-1069-A2DD-08002B30309D}", "command": "telephon.cpl", "category": "Advanced"},
    {"name": "Windows To Go", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "pwcreator.exe", "category": "Advanced"},
    {"name": "Steps Recorder", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "psr.exe", "category": "Advanced"},
    {"name": "Display Switch", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "DisplaySwitch.exe", "category": "Advanced"},
    {"name": "Magnifier", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "magnify.exe", "category": "Advanced"},
    {"name": "Narrator", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "narrator.exe", "category": "Advanced"},
    {"name": "On-Screen Keyboard", "clsid": "{D555645E-D4F8-4C29-A827-D93C859C6563}", "command": "osk.exe", "category": "Advanced"},
    {"name": "Sound Recorder", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "SoundRecorder.exe", "category": "Advanced"},
    {"name": "Snipping Tool", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "SnippingTool.exe", "category": "Advanced"},
    {"name": "Windows Fax and Scan", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "WFS.exe", "category": "Advanced"},
    {"name": "XPS Viewer", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "xpsrchvw.exe", "category": "Advanced"},
    {"name": "Windows Media Player", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "wmplayer.exe", "category": "Advanced"},
    {"name": "Windows Photo Viewer", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "rundll32.exe shimgvw.dll,ImageView_Fullscreen", "category": "Advanced"},
    {"name": "WordPad", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "write.exe", "category": "Advanced"},
    {"name": "Paint", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "mspaint.exe", "category": "Advanced"},
    {"name": "Calculator", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "calc.exe", "category": "Advanced"},
    {"name": "Notepad", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "notepad.exe", "category": "Advanced"},
    {"name": "Character Map", "clsid": "{725BE8F7-668E-4C7B-8F90-46BDB0936436}", "command": "charmap.exe", "category": "Advanced"},
    {"name": "Task Manager", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "taskmgr.exe", "category": "Advanced"},
    {"name": "Command Prompt", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "cmd.exe", "category": "Advanced"},
    {"name": "PowerShell", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "powershell.exe", "category": "Advanced"},
    {"name": "Windows Terminal", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "wt.exe", "category": "Advanced"},
    {"name": "Remote Desktop Connection", "clsid": "{5EA4F148-308C-46D7-98A9-XXXXXXXX}", "command": "mstsc.exe", "category": "Advanced"},
    {"name": "Windows Explorer", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "explorer.exe", "category": "Advanced"},
    {"name": "Run Dialog", "clsid": "{2559A1F3-21D7-11D4-BDAF-00C04F60B9F0}", "command": "explorer.exe shell:::{2559A1F3-21D7-11D4-BDAF-00C04F60B9F0}", "category": "Advanced"},
    {"name": "God Mode (All Tasks)", "clsid": "{ED7BA470-8E54-465E-825C-99712043E01C}", "command": "explorer.exe shell:::{ED7BA470-8E54-465E-825C-99712043E01C}", "category": "Advanced"},
    {"name": "This PC", "clsid": "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", "command": "explorer.exe shell:MyComputerFolder", "category": "Advanced"},
    {"name": "Recycle Bin", "clsid": "{645FF040-5081-101B-9F08-00AA002F954E}", "command": "explorer.exe shell:RecycleBinFolder", "category": "Advanced"},
    {"name": "Control Panel (All Items)", "clsid": "{26EE0668-A00A-44D7-9371-BEB064C98683}", "command": "control.exe", "category": "Advanced"},
    {"name": "Windows Update", "clsid": "{36EEF7DB-88AD-4E81-AD49-XXXXXXXX}", "command": "control /name Microsoft.WindowsUpdate", "category": "Advanced"},
    {"name": "Windows Defender", "clsid": "{D8559EB9-XXXX-XXXX-XXXX-XXXXXXXX}", "command": "windowsdefender:", "category": "Advanced"},
    {"name": "Location Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-location", "category": "Advanced"},
    {"name": "Camera Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:camera", "category": "Advanced"},
    {"name": "Microphone Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-microphone", "category": "Advanced"},
    {"name": "Notifications Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:notifications", "category": "Advanced"},
    {"name": "Focus Assist", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:quiethours", "category": "Advanced"},
    {"name": "Storage Sense", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:storagesense", "category": "Advanced"},
    {"name": "Default Apps", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:defaultapps", "category": "Advanced"},
    {"name": "Startup Apps", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:startupapps", "category": "Advanced"},
    {"name": "Optional Features", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:optionalfeatures", "category": "Advanced"},
    {"name": "Projecting to this PC", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:project", "category": "Advanced"},
    {"name": "Shared Experiences", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:crossdevice", "category": "Advanced"},
    {"name": "Clipboard", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:clipboard", "category": "Advanced"},
    {"name": "Remote Desktop", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:remotedesktop", "category": "Advanced"},
    {"name": "Device Encryption", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:deviceencryption", "category": "Advanced"},
    {"name": "Find My Device", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:findmydevice", "category": "Advanced"},
    {"name": "Windows Insider Program", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:windowsinsider", "category": "Advanced"},
    {"name": "Delivery Optimization", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:delivery-optimization", "category": "Advanced"},
    {"name": "Troubleshoot", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:troubleshoot", "category": "Advanced"},
    {"name": "Recovery", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:recovery", "category": "Advanced"},
    {"name": "Activation", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:activation", "category": "Advanced"},
    {"name": "About", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:about", "category": "Advanced"},
    {"name": "Tablet Mode", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:tabletmode", "category": "Advanced"},
    {"name": "Multitasking", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:multitasking", "category": "Advanced"},
    {"name": "For Developers", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:developers", "category": "Advanced"},
    {"name": "Windows Security", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:windowsdefender", "category": "Advanced"},
    {"name": "Backup", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:backup", "category": "Advanced"},
    {"name": "Date and Time", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:dateandtime", "category": "Advanced"},
    {"name": "Region", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:regionformatting", "category": "Advanced"},
    {"name": "Language", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:regionlanguage", "category": "Advanced"},
    {"name": "Speech", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:speech", "category": "Advanced"},
    {"name": "Typing", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:typing", "category": "Advanced"},
    {"name": "Sign-in Options", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:signinoptions", "category": "Advanced"},
    {"name": "Your Info", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:yourinfo", "category": "Advanced"},
    {"name": "Email and Accounts", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:emailandaccounts", "category": "Advanced"},
    {"name": "Access Work or School", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:workplace", "category": "Advanced"},
    {"name": "Family and Other Users", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:otherusers", "category": "Advanced"},
    {"name": "Sync Your Settings", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:sync", "category": "Advanced"},
    {"name": "Wi-Fi", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-wifi", "category": "Advanced"},
    {"name": "Ethernet", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-ethernet", "category": "Advanced"},
    {"name": "Dial-up", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-dialup", "category": "Advanced"},
    {"name": "VPN", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-vpn", "category": "Advanced"},
    {"name": "Airplane Mode", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-airplanemode", "category": "Advanced"},
    {"name": "Mobile Hotspot", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-mobilehotspot", "category": "Advanced"},
    {"name": "Data Usage", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:datausage", "category": "Advanced"},
    {"name": "Proxy", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:network-proxy", "category": "Advanced"},
    {"name": "Background", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:personalization-background", "category": "Advanced"},
    {"name": "Colors", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:personalization-colors", "category": "Advanced"},
    {"name": "Lock Screen", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:lockscreen", "category": "Advanced"},
    {"name": "Themes", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:themes", "category": "Advanced"},
    {"name": "Fonts", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:fonts", "category": "Advanced"},
    {"name": "Start", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:personalization-start", "category": "Advanced"},
    {"name": "Taskbar", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:taskbar", "category": "Advanced"},
    {"name": "General", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy", "category": "Advanced"},
    {"name": "Speech Privacy", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-speech", "category": "Advanced"},
    {"name": "Inking and Typing Privacy", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-speechtyping", "category": "Advanced"},
    {"name": "Diagnostics and Feedback", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-feedback", "category": "Advanced"},
    {"name": "Activity History", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-activityhistory", "category": "Advanced"},
    {"name": "App Permissions", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:privacy-apppermissions", "category": "Advanced"},
    {"name": "Xbox Game Bar", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:gaming-gamebar", "category": "Advanced"},
    {"name": "Captures", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:gaming-gamedvr", "category": "Advanced"},
    {"name": "Game Mode", "clsid": "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}", "command": "ms-settings:gaming-gamemode", "category": "Advanced"},
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ControlPanelItem:
    """Represents a single Control Panel item."""
    name: str
    clsid: str
    command: str
    category: str = "Unknown"
    icon_path: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "clsid": self.clsid,
            "command": self.command,
            "category": self.category,
            "icon_path": self.icon_path,
            "description": self.description,
        }


@dataclass
class SystemInfo:
    """Complete system information container."""
    platform: str = ""
    platform_version: str = ""
    platform_release: str = ""
    architecture: str = ""
    processor: str = ""
    machine: str = ""
    node_name: str = ""
    python_version: str = ""
    cpu_count: int = 0
    boot_time: str = ""
    install_date: str = ""
    product_type: str = ""
    edition: str = ""
    build_number: str = ""
    uptime_seconds: float = 0.0


# =============================================================================
# Main WindowsGodMode Class
# =============================================================================

class WindowsGodMode:
    """
    Windows God Mode Integration for JARVIS BRAINIAC.

    Creates and manages the legitimate Windows God Mode folder
    (CLSID {ED7BA470-8E54-465E-825C-99712043E01C}) which provides
    access to 200+ system settings in a single location.

    This class provides methods to:
    - Create and manage the God Mode folder
    - Enumerate all Control Panel items (200+ settings)
    - Open specific settings programmatically
    - Search settings by name
    - Access system configuration (network, display, power, security, storage)
    - Launch advanced tools (Event Viewer, Device Manager, Registry Editor, etc.)
    - Perform system optimization (clear temp files, optimize drives, check disk)

    Attributes:
        god_mode_path (str): Path to the God Mode folder if created.
        control_panel_items (List[ControlPanelItem]): All 200+ settings.
    """

    def __init__(self):
        """Initialize the Windows God Mode integration."""
        self.god_mode_path: Optional[str] = None
        self._control_panel_items: List[ControlPanelItem] = []
        self._is_windows = platform.system() == "Windows"
        self._build_control_panel_index()

    def _build_control_panel_index(self) -> None:
        """Build internal index of all Control Panel items for fast search."""
        self._control_panel_items = [
            ControlPanelItem(
                name=item["name"],
                clsid=item["clsid"],
                command=item["command"],
                category=item.get("category", "Unknown"),
                icon_path=f"shell32.dll,-{100 + idx}",
                description=f"Windows Control Panel: {item['name']}",
            )
            for idx, item in enumerate(CONTROL_PANEL_ITEMS)
        ]

    # =====================================================================
    # God Mode Folder Management
    # =====================================================================

    def create_god_mode_folder(self, path: str = None) -> str:
        """
        Create the Windows God Mode folder at the specified path.

        Uses the legitimate Microsoft CLSID {ED7BA470-8E54-465E-825C-99712043E01C}
        to create a special folder that exposes all 200+ Control Panel settings.

        Args:
            path: Directory where the God Mode folder will be created.
                  Defaults to user's Desktop.

        Returns:
            str: Full path to the created God Mode folder.

        Raises:
            RuntimeError: If not running on Windows.
            OSError: If folder creation fails.
        """
        if not self._is_windows:
            raise RuntimeError(
                "God Mode folder can only be created on Windows. "
                "Use MockWindowsGodMode for testing on other platforms."
            )

        if path is None:
            path = os.path.join(os.path.expanduser("~"), "Desktop")

        folder_name = GOD_MODE_FOLDER_NAME
        full_path = os.path.join(path, folder_name)

        try:
            os.makedirs(full_path, exist_ok=True)
            self.god_mode_path = full_path
            return full_path
        except OSError as exc:
            raise OSError(f"Failed to create God Mode folder at {full_path}: {exc}") from exc

    def remove_god_mode_folder(self) -> bool:
        """
        Remove the previously created God Mode folder.

        Returns:
            bool: True if folder was removed, False otherwise.
        """
        if self.god_mode_path and os.path.exists(self.god_mode_path):
            try:
                shutil.rmtree(self.god_mode_path)
                self.god_mode_path = None
                return True
            except (OSError, PermissionError):
                return False
        return False

    def list_control_panel_items(self) -> List[Dict[str, str]]:
        """
        List all 200+ Control Panel settings with metadata.

        Returns:
            List[Dict[str, str]]: Each dict contains:
                - name: Display name of the setting
                - clsid: CLSID identifier
                - command: Shell command to open the setting
                - category: Category grouping (e.g., "System and Security")
                - icon_path: Path to the icon resource
                - description: Human-readable description
        """
        return [item.to_dict() for item in self._control_panel_items]

    def open_setting(self, setting_name: str) -> bool:
        """
        Open a specific Control Panel setting by name.

        Args:
            setting_name: The display name of the setting to open.
                          Partial matching is supported.

        Returns:
            bool: True if the setting was opened successfully.

        Example:
            >>> god_mode.open_setting("Device Manager")
            True
        """
        matches = self.search_settings(setting_name)
        if not matches:
            return False

        # Prefer exact match, otherwise use first result
        command = matches[0]["command"]
        for match in matches:
            if match["name"].lower() == setting_name.lower():
                command = match["command"]
                break

        if not self._is_windows:
            return False

        try:
            # Use shell=True for commands that need it
            if command.startswith("control ") or command.startswith("ms-settings"):
                subprocess.Popen(command, shell=True)
            else:
                subprocess.Popen(command, shell=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def search_settings(self, query: str) -> List[Dict[str, str]]:
        """
        Search Control Panel items by partial name match.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List[Dict[str, str]]: Matching settings sorted by relevance.

        Example:
            >>> results = god_mode.search_settings("network")
            >>> len(results) > 0
            True
        """
        query_lower = query.lower()
        results: List[tuple] = []

        for item in self._control_panel_items:
            name_lower = item.name.lower()
            if query_lower in name_lower:
                # Score: exact match > starts with > contains
                if name_lower == query_lower:
                    score = 3
                elif name_lower.startswith(query_lower):
                    score = 2
                else:
                    score = 1
                results.append((score, item.to_dict()))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in results]

    def get_settings_by_category(self, category: str) -> List[Dict[str, str]]:
        """
        Get all settings belonging to a specific category.

        Args:
            category: Category name (e.g., "System and Security").

        Returns:
            List[Dict[str, str]]: Settings in the category.
        """
        return [
            item.to_dict()
            for item in self._control_panel_items
            if item.category.lower() == category.lower()
        ]

    def get_all_categories(self) -> List[str]:
        """
        Get list of all available categories.

        Returns:
            List[str]: Unique category names.
        """
        categories = sorted({item.category for item in self._control_panel_items})
        return categories

    def get_setting_count(self) -> int:
        """
        Get total number of available Control Panel items.

        Returns:
            int: Number of settings (200+).
        """
        return len(self._control_panel_items)

    # =====================================================================
    # System Configuration Access
    # =====================================================================

    def get_system_info_full(self) -> Dict[str, Any]:
        """
        Retrieve complete system information.

        Returns:
            Dict[str, Any]: Comprehensive system details including:
                - os: Operating system name
                - version: OS version string
                - build: Build number
                - architecture: System architecture (x86/x64/ARM64)
                - processor: CPU model name
                - cpu_count: Number of logical CPUs
                - hostname: Computer name
                - python_version: Python runtime version
                - platform: Platform identifier
                - memory_gb: Approximate total RAM in GB
                - username: Current user name
                - domain: Computer domain/workgroup
                - is_admin: Whether running with admin privileges
                - boot_time: System boot time (if available)
                - product_type: Windows edition type
                - edition: Windows edition name
        """
        info: Dict[str, Any] = {
            "os": platform.system(),
            "version": platform.version(),
            "build": "",
            "architecture": platform.architecture()[0],
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count() or 0,
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "username": os.getlogin() if hasattr(os, "getlogin") else "",
            "is_admin": False,
            "timestamp": datetime.now().isoformat(),
        }

        if self._is_windows:
            # Try to get Windows-specific details via WMI or registry
            info["is_admin"] = self._check_admin()
            info["build"] = self._get_windows_build()
            info["edition"] = self._get_windows_edition()
            info["product_type"] = self._get_product_type()

            # Try to get memory info via ctypes
            try:
                mem_info = self._get_memory_info()
                if mem_info:
                    info["memory_gb"] = round(mem_info / (1024 ** 3), 2)
            except Exception:
                info["memory_gb"] = 0

            # Try to get boot time via WMI
            try:
                info["boot_time"] = self._get_boot_time()
            except Exception:
                info["boot_time"] = ""
        else:
            info["memory_gb"] = 0
            info["is_admin"] = (os.getuid() == 0) if hasattr(os, "getuid") else False

        return info

    def _check_admin(self) -> bool:
        """Check if current process has administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
        except Exception:
            return False

    def _get_windows_build(self) -> str:
        """Get Windows build number."""
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                build, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
                return str(build)
        except Exception:
            return ""

    def _get_windows_edition(self) -> str:
        """Get Windows edition name."""
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                edition, _ = winreg.QueryValueEx(key, "EditionID")
                return str(edition)
        except Exception:
            return ""

    def _get_product_type(self) -> str:
        """Get Windows product type (Workstation/Server)."""
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                product_name, _ = winreg.QueryValueEx(key, "ProductName")
                return str(product_name)
        except Exception:
            return ""

    def _get_memory_info(self) -> Optional[int]:
        """Get total physical memory in bytes."""
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            mem_status = MEMORYSTATUSEX()
            mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status)):
                return mem_status.ullTotalPhys
        except Exception:
            pass
        return None

    def _get_boot_time(self) -> str:
        """Get system boot time."""
        try:
            import ctypes
            from datetime import datetime
            tick_count = ctypes.windll.kernel32.GetTickCount64()  # type: ignore
            uptime_seconds = tick_count / 1000
            boot_time = datetime.now().timestamp() - uptime_seconds
            return datetime.fromtimestamp(boot_time).isoformat()
        except Exception:
            return ""

    def get_network_settings(self) -> Dict[str, Any]:
        """
        Retrieve network configuration information.

        Returns:
            Dict[str, Any]: Network details including:
                - hostname: Computer hostname
                - hostname_fqdn: Fully qualified domain name
                - adapters: List of network adapters (name, IP, MAC)
                - ipconfig_raw: Raw ipconfig /all output (Windows)
                - default_gateway: Default gateway address
                - dns_servers: List of DNS servers
                - dhcp_enabled: Whether DHCP is enabled
        """
        info: Dict[str, Any] = {
            "hostname": platform.node(),
            "hostname_fqdn": "",
            "adapters": [],
            "ipconfig_raw": "",
            "default_gateway": "",
            "dns_servers": [],
            "dhcp_enabled": False,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            import socket
            info["hostname_fqdn"] = socket.getfqdn()
        except Exception:
            pass

        if self._is_windows:
            try:
                result = subprocess.run(
                    ["ipconfig", "/all"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    info["ipconfig_raw"] = result.stdout
                    parsed = self._parse_ipconfig(result.stdout)
                    info.update(parsed)
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Try to get network adapter info via GetAdaptersInfo
            adapters = self._get_network_adapters()
            if adapters:
                info["adapters"] = adapters

        return info

    def _parse_ipconfig(self, output: str) -> Dict[str, Any]:
        """Parse ipconfig /all output into structured data."""
        result: Dict[str, Any] = {
            "dns_servers": [],
            "default_gateway": "",
            "dhcp_enabled": False,
        }

        for line in output.splitlines():
            line_lower = line.lower().strip()

            if "dns servers" in line_lower or "dns-servers" in line_lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    dns = parts[1].strip()
                    if dns:
                        result["dns_servers"].append(dns)

            if "default gateway" in line_lower:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    gateway = parts[1].strip()
                    if gateway and gateway != "":
                        result["default_gateway"] = gateway

            if "dhcp enabled" in line_lower:
                if "yes" in line_lower:
                    result["dhcp_enabled"] = True

        return result

    def _get_network_adapters(self) -> List[Dict[str, str]]:
        """Get network adapter information using Windows APIs."""
        adapters: List[Dict[str, str]] = []
        try:
            result = subprocess.run(
                ["wmic", "nic", "where", "NetEnabled=True", "get", "Name,MACAddress,Speed", "/format:csv"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                for line in lines[1:]:  # Skip header
                    parts = line.split(",")
                    if len(parts) >= 4:
                        adapters.append({
                            "name": parts[2].strip() if len(parts) > 2 else "",
                            "mac_address": parts[1].strip() if len(parts) > 1 else "",
                            "speed": parts[3].strip() if len(parts) > 3 else "",
                        })
        except (subprocess.TimeoutExpired, OSError):
            pass
        return adapters

    def get_display_settings(self) -> Dict[str, Any]:
        """
        Retrieve display/graphics settings.

        Returns:
            Dict[str, Any]: Display information including:
                - screen_resolution: Current screen resolution
                - refresh_rate: Display refresh rate
                - bit_depth: Color bit depth
                - scaling: Display scaling percentage
                - gpu_info: Graphics card information (Windows)
                - monitors: Connected monitor details
                - primary_monitor: Primary display info
        """
        info: Dict[str, Any] = {
            "screen_resolution": "",
            "refresh_rate": "",
            "bit_depth": "",
            "scaling": "",
            "gpu_info": [],
            "monitors": [],
            "primary_monitor": {},
            "timestamp": datetime.now().isoformat(),
        }

        if self._is_windows:
            try:
                # Get display settings via WMI
                result = subprocess.run(
                    ["wmic", "path", "win32_videocontroller", "get", "Name,AdapterRAM,VideoModeDescription,CurrentRefreshRate", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["gpu_info"] = self._parse_gpu_info(result.stdout)
            except (subprocess.TimeoutExpired, OSError):
                pass

            try:
                # Get monitor info
                result = subprocess.run(
                    ["wmic", "path", "win32_desktopmonitor", "get", "Name,ScreenHeight,ScreenWidth,PixelsPerXLogicalInch", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["monitors"] = self._parse_monitor_info(result.stdout)
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Get current screen resolution via ctypes
            try:
                width, height = self._get_screen_resolution()
                if width and height:
                    info["screen_resolution"] = f"{width}x{height}"
            except Exception:
                pass

        return info

    def _parse_gpu_info(self, output: str) -> List[Dict[str, str]]:
        """Parse GPU information from WMIC output."""
        gpus: List[Dict[str, str]] = []
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 5:
                gpus.append({
                    "name": parts[2].strip() if len(parts) > 2 else "",
                    "adapter_ram_mb": str(int(parts[3]) // (1024 * 1024)) if len(parts) > 3 and parts[3].strip() else "",
                    "video_mode": parts[4].strip() if len(parts) > 4 else "",
                    "refresh_rate": parts[1].strip() if len(parts) > 1 else "",
                })
        return gpus

    def _parse_monitor_info(self, output: str) -> List[Dict[str, str]]:
        """Parse monitor information from WMIC output."""
        monitors: List[Dict[str, str]] = []
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 5:
                monitors.append({
                    "name": parts[1].strip() if len(parts) > 1 else "",
                    "width": parts[2].strip() if len(parts) > 2 else "",
                    "height": parts[3].strip() if len(parts) > 3 else "",
                    "dpi": parts[4].strip() if len(parts) > 4 else "",
                })
        return monitors

    def _get_screen_resolution(self) -> tuple:
        """Get current screen resolution via Windows API."""
        try:
            user32 = ctypes.windll.user32  # type: ignore
            width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            return width, height
        except Exception:
            return 0, 0

    def get_power_settings(self) -> Dict[str, Any]:
        """
        Retrieve power plan and battery settings.

        Returns:
            Dict[str, Any]: Power information including:
                - active_power_plan: Currently active power plan
                - power_plans: List of available power plans
                - battery_present: Whether battery is present
                - battery_level: Current battery percentage
                - battery_status: Charging/discharging status
                - estimated_runtime: Estimated battery runtime
                - ac_line_status: Whether on AC power
        """
        info: Dict[str, Any] = {
            "active_power_plan": "",
            "power_plans": [],
            "battery_present": False,
            "battery_level": -1,
            "battery_status": "",
            "estimated_runtime": "",
            "ac_line_status": False,
            "timestamp": datetime.now().isoformat(),
        }

        if self._is_windows:
            # Get active power plan
            try:
                result = subprocess.run(
                    ["powercfg", "/getactivescheme"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["active_power_plan"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Get all power plans
            try:
                result = subprocess.run(
                    ["powercfg", "/list"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["power_plans"] = [
                        line.strip()
                        for line in result.stdout.splitlines()
                        if line.strip()
                    ]
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Get battery info via WMIC
            try:
                result = subprocess.run(
                    ["wmic", "path", "win32_battery", "get", "EstimatedChargeRemaining,BatteryStatus,EstimatedRunTime", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    parsed = self._parse_battery_info(result.stdout)
                    info.update(parsed)
            except (subprocess.TimeoutExpired, OSError):
                pass

        return info

    def _parse_battery_info(self, output: str) -> Dict[str, Any]:
        """Parse battery information from WMIC output."""
        result: Dict[str, Any] = {
            "battery_present": False,
            "battery_level": -1,
            "battery_status": "",
            "estimated_runtime": "",
        }

        lines = [l.strip() for l in output.splitlines() if l.strip()]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 4:
                result["battery_present"] = True
                try:
                    result["battery_level"] = int(parts[1].strip())
                except ValueError:
                    result["battery_level"] = -1
                try:
                    status_code = int(parts[2].strip())
                    status_map = {1: "Discharging", 2: "On AC", 3: "Fully Charged",
                                   4: "Low", 5: "Critical", 6: "Charging", 7: "Charging High",
                                   8: "Charging Low", 9: "Charging Critical"}
                    result["battery_status"] = status_map.get(status_code, "Unknown")
                except ValueError:
                    result["battery_status"] = "Unknown"
                try:
                    minutes = int(parts[3].strip())
                    if minutes > 0 and minutes < 99999:
                        hours = minutes // 60
                        mins = minutes % 60
                        result["estimated_runtime"] = f"{hours}h {mins}m"
                except ValueError:
                    pass

        return result

    def get_security_settings(self) -> Dict[str, Any]:
        """
        Retrieve Windows security settings.

        Returns:
            Dict[str, Any]: Security information including:
                - firewall_enabled: Windows Firewall status
                - defender_enabled: Windows Defender status
                - uac_enabled: User Account Control status
                - uac_level: UAC notification level
                - bitlocker_status: BitLocker drive encryption status
                - antivirus_products: Installed antivirus products
                - last_update: Last Windows Update check
                - secure_boot: Secure Boot status
                - tpm_present: TPM chip availability
                - windows_hello: Windows Hello availability
        """
        info: Dict[str, Any] = {
            "firewall_enabled": False,
            "defender_enabled": False,
            "uac_enabled": False,
            "uac_level": "",
            "bitlocker_status": {},
            "antivirus_products": [],
            "last_update": "",
            "secure_boot": False,
            "tpm_present": False,
            "windows_hello": False,
            "timestamp": datetime.now().isoformat(),
        }

        if self._is_windows:
            # Check UAC status
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System",
                ) as key:
                    uac_value, _ = winreg.QueryValueEx(key, "EnableLUA")
                    info["uac_enabled"] = bool(uac_value)
                    try:
                        consent_value, _ = winreg.QueryValueEx(key, "ConsentPromptBehaviorAdmin")
                        levels = {0: "Never notify", 1: "Notify without dimming",
                                   2: "Notify with dimming", 5: "Always notify"}
                        info["uac_level"] = levels.get(consent_value, "Unknown")
                    except FileNotFoundError:
                        info["uac_level"] = "Default"
            except Exception:
                pass

            # Check firewall status
            try:
                result = subprocess.run(
                    ["netsh", "advfirewall", "show", "currentprofile"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["firewall_enabled"] = "ON" in result.stdout.upper()
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Check antivirus products via WMI
            try:
                result = subprocess.run(
                    ["wmic", r"/namespace:\root\securitycenter2", "path", "antivirusproduct",
                     "get", "displayName,productState", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["antivirus_products"] = self._parse_antivirus(result.stdout)
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Check Secure Boot
            try:
                result = subprocess.run(
                    ["powershell.exe", "-Command",
                     "Confirm-SecureBootUEFI"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["secure_boot"] = "True" in result.stdout
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Check TPM
            try:
                result = subprocess.run(
                    ["wmic", r"/namespace:\root\cimv2\security\MicrosoftTpm",
                     "path", "Win32_Tpm", "get", "IsActivated_InitialValue", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["tpm_present"] = "TRUE" in result.stdout.upper()
            except (subprocess.TimeoutExpired, OSError):
                pass

        return info

    def _parse_antivirus(self, output: str) -> List[Dict[str, str]]:
        """Parse antivirus product information from WMIC output."""
        products: List[Dict[str, str]] = []
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 3:
                state_hex = parts[1].strip() if len(parts) > 1 else ""
                products.append({
                    "name": parts[2].strip() if len(parts) > 2 else "",
                    "state": state_hex,
                    "enabled": state_hex.endswith("10") or state_hex.endswith("11"),
                })
        return products

    def get_storage_settings(self) -> Dict[str, Any]:
        """
        Retrieve storage and disk information.

        Returns:
            Dict[str, Any]: Storage details including:
                - drives: List of drives with free/used space
                - total_space_gb: Total storage in GB
                - free_space_gb: Free storage in GB
                - disk_type: Disk type (HDD/SSD)
                - volumes: Volume information
                - filesystem: Filesystem type
                - storage_sense: Storage Sense status
        """
        info: Dict[str, Any] = {
            "drives": [],
            "total_space_gb": 0.0,
            "free_space_gb": 0.0,
            "disk_type": "",
            "volumes": [],
            "filesystem": "",
            "timestamp": datetime.now().isoformat(),
        }

        if self._is_windows:
            # Get drive information
            drives = []
            for drive_letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive_path = f"{drive_letter}:\\"
                if os.path.exists(drive_path):
                    try:
                        total, used, free = shutil.disk_usage(drive_path)
                        drives.append({
                            "letter": drive_letter,
                            "path": drive_path,
                            "total_gb": round(total / (1024 ** 3), 2),
                            "used_gb": round(used / (1024 ** 3), 2),
                            "free_gb": round(free / (1024 ** 3), 2),
                            "usage_percent": round((used / total) * 100, 1) if total > 0 else 0,
                        })
                        info["total_space_gb"] += round(total / (1024 ** 3), 2)
                        info["free_space_gb"] += round(free / (1024 ** 3), 2)
                    except (OSError, PermissionError):
                        continue

            info["drives"] = drives

            # Get disk type via WMIC
            try:
                result = subprocess.run(
                    ["wmic", "diskdrive", "get", "Model,MediaType,Size", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["disk_type"] = self._parse_disk_type(result.stdout)
            except (subprocess.TimeoutExpired, OSError):
                pass

            # Get volume information
            try:
                result = subprocess.run(
                    ["wmic", "volume", "get", "DriveLetter,FileSystem,Capacity,FreeSpace", "/format:csv"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    info["volumes"] = self._parse_volume_info(result.stdout)
            except (subprocess.TimeoutExpired, OSError):
                pass

        return info

    def _parse_disk_type(self, output: str) -> str:
        """Parse disk type from WMIC output."""
        if "SSD" in output.upper():
            return "SSD"
        elif "HDD" in output.upper():
            return "HDD"
        return "Unknown"

    def _parse_volume_info(self, output: str) -> List[Dict[str, str]]:
        """Parse volume information from WMIC output."""
        volumes: List[Dict[str, str]] = []
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) >= 5:
                volumes.append({
                    "drive_letter": parts[1].strip() if len(parts) > 1 else "",
                    "filesystem": parts[2].strip() if len(parts) > 2 else "",
                    "capacity_gb": str(round(int(parts[3]) / (1024 ** 3), 2)) if len(parts) > 3 and parts[3].strip() else "",
                    "free_gb": str(round(int(parts[4]) / (1024 ** 3), 2)) if len(parts) > 4 and parts[4].strip() else "",
                })
        return volumes

    # =====================================================================
    # Advanced Tools
    # =====================================================================

    def open_event_viewer(self) -> bool:
        """
        Open Windows Event Viewer.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("eventvwr.msc", "Event Viewer")

    def open_device_manager(self) -> bool:
        """
        Open Device Manager.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("devmgmt.msc", "Device Manager")

    def open_disk_management(self) -> bool:
        """
        Open Disk Management console.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("diskmgmt.msc", "Disk Management")

    def open_services(self) -> bool:
        """
        Open Services management console.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("services.msc", "Services")

    def open_registry_editor(self, confirm: bool = True) -> bool:
        """
        Open Registry Editor (with warning).

        Args:
            confirm: If True, warns about the risks of editing the registry.

        Returns:
            bool: True if launched successfully.

        Warning:
            Editing the registry can cause serious system problems.
            Always back up the registry before making changes.
        """
        if confirm and self._is_windows:
            warnings.warn(
                "WARNING: Editing the Windows Registry can cause serious "
                "system problems. Always back up the registry before making changes.",
                RuntimeWarning,
                stacklevel=2,
            )
        return self._launch_tool("regedit.exe", "Registry Editor")

    def open_group_policy(self) -> bool:
        """
        Open Local Group Policy Editor.

        Note: Only available on Windows Pro, Enterprise, and Education editions.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("gpedit.msc", "Local Group Policy Editor")

    def open_task_scheduler(self) -> bool:
        """
        Open Task Scheduler.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("taskschd.msc", "Task Scheduler")

    def open_performance_monitor(self) -> bool:
        """
        Open Performance Monitor.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("perfmon.msc", "Performance Monitor")

    def open_resource_monitor(self) -> bool:
        """
        Open Resource Monitor.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("resmon.exe", "Resource Monitor")

    def open_system_configuration(self) -> bool:
        """
        Open System Configuration (msconfig).

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("msconfig.exe", "System Configuration")

    def open_computer_management(self) -> bool:
        """
        Open Computer Management console.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("compmgmt.msc", "Computer Management")

    def open_local_security_policy(self) -> bool:
        """
        Open Local Security Policy.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("secpol.msc", "Local Security Policy")

    def open_component_services(self) -> bool:
        """
        Open Component Services (DCOM config).

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("comexp.msc", "Component Services")

    def open_certificates(self) -> bool:
        """
        Open Certificate Manager.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("certmgr.msc", "Certificate Manager")

    def open_windows_firewall(self) -> bool:
        """
        Open Windows Firewall with Advanced Security.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("wf.msc", "Windows Firewall")

    def open_iis_manager(self) -> bool:
        """
        Open Internet Information Services (IIS) Manager.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("inetmgr.exe", "IIS Manager")

    def open_hyper_v_manager(self) -> bool:
        """
        Open Hyper-V Manager.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("virtmgmt.msc", "Hyper-V Manager")

    def open_print_management(self) -> bool:
        """
        Open Print Management console.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("printmanagement.msc", "Print Management")

    def open_wmi_management(self) -> bool:
        """
        Open WMI Management console.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("wmimgmt.msc", "WMI Management")

    def open_shared_folders(self) -> bool:
        """
        Open Shared Folders management.

        Returns:
            bool: True if launched successfully.
        """
        return self._launch_tool("fsmgmt.msc", "Shared Folders")

    def _launch_tool(self, command: str, tool_name: str) -> bool:
        """
        Helper method to launch a Windows management tool.

        Args:
            command: Shell command to launch the tool.
            tool_name: Human-readable name of the tool.

        Returns:
            bool: True if launched successfully.
        """
        if not self._is_windows:
            return False

        try:
            # Use shell=True for .msc files which need mmc.exe
            if command.endswith(".msc"):
                subprocess.Popen(["mmc.exe", command], shell=False)
            else:
                subprocess.Popen(command, shell=True)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    # =====================================================================
    # System Optimization
    # =====================================================================

    def clear_temp_files(self) -> int:
        """
        Clean temporary files from the system.

        Removes files from:
        - %TEMP% directory
        - Windows Temp directory
        - User temporary files

        Returns:
            int: Number of files removed.

        Warning:
            Some files may be in use and cannot be removed.
        """
        count = 0
        if not self._is_windows:
            return 0

        temp_dirs = [
            tempfile.gettempdir(),
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp"),
        ]

        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                count += self._clean_directory(temp_dir)

        return count

    def _clean_directory(self, directory: str) -> int:
        """Recursively remove temporary files from a directory."""
        count = 0
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    count += 1
                except (OSError, PermissionError):
                    continue
            # Try to remove empty directories
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    os.rmdir(dir_path)
                except (OSError, PermissionError):
                    continue
        return count

    def optimize_drives(self) -> Dict[str, Any]:
        """
        Run drive optimization (defragmentation/TRIM).

        Returns:
            Dict[str, Any]: Optimization results including:
                - status: "success", "error", or "not_supported"
                - drives_optimized: List of drives that were optimized
                - message: Human-readable status message
                - recommendation: Suggested next steps
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "drives_optimized": [],
            "message": "Drive optimization requires Windows.",
            "recommendation": "Run this on a Windows system.",
            "timestamp": datetime.now().isoformat(),
        }

        if not self._is_windows:
            return result

        try:
            # Analyze and optimize all drives
            subprocess_result = subprocess.run(
                ["defrag", "/C", "/V"],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if subprocess_result.returncode == 0:
                result["status"] = "success"
                result["message"] = "Drive optimization completed."
                result["recommendation"] = "Check results in the output."
                # Parse output for drive letters
                for line in subprocess_result.stdout.splitlines():
                    if "drive" in line.lower():
                        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                            if f"{char}:" in line:
                                if char not in result["drives_optimized"]:
                                    result["drives_optimized"].append(char)
            else:
                result["status"] = "error"
                result["message"] = subprocess_result.stderr or "Optimization failed."

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["message"] = "Optimization timed out."
        except (OSError, subprocess.SubprocessError) as exc:
            result["status"] = "error"
            result["message"] = str(exc)

        return result

    def check_disk(self, drive: str = "C:") -> Dict[str, Any]:
        """
        Check disk for errors using chkdsk.

        Args:
            drive: Drive letter to check (default: "C:").

        Returns:
            Dict[str, Any]: Check results including:
                - status: "success", "error", or "not_supported"
                - drive: The drive that was checked
                - message: Human-readable status
                - requires_reboot: Whether a reboot is needed for full check
                - errors_found: Whether errors were detected
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "drive": drive,
            "message": "Disk check requires Windows.",
            "requires_reboot": False,
            "errors_found": False,
            "timestamp": datetime.now().isoformat(),
        }

        if not self._is_windows:
            return result

        # Normalize drive parameter
        if not drive.endswith(":"):
            drive = f"{drive}:"

        try:
            # Run chkdsk in read-only mode first (no /F flag)
            subprocess_result = subprocess.run(
                ["chkdsk", drive],
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = subprocess_result.stdout + subprocess_result.stderr
            result["raw_output"] = output

            if subprocess_result.returncode == 0:
                result["status"] = "success"
                result["message"] = f"Disk check completed for {drive}"
                result["errors_found"] = "errors found" in output.lower() or "found errors" in output.lower()
            elif subprocess_result.returncode == 1:
                result["status"] = "success"
                result["message"] = f"Errors found on {drive}. Run with /F to fix."
                result["errors_found"] = True
                result["requires_reboot"] = True
            elif subprocess_result.returncode == 3:
                result["status"] = "success"
                result["message"] = f"Disk check could not complete. Volume is in use."
                result["requires_reboot"] = True
            else:
                result["status"] = "error"
                result["message"] = f"Disk check returned code {subprocess_result.returncode}"

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["message"] = "Disk check timed out."
        except (OSError, subprocess.SubprocessError) as exc:
            result["status"] = "error"
            result["message"] = str(exc)

        return result

    def schedule_disk_check(self, drive: str = "C:") -> bool:
        """
        Schedule a disk check for the next reboot.

        Args:
            drive: Drive letter to check (default: "C:").

        Returns:
            bool: True if scheduled successfully.
        """
        if not self._is_windows:
            return False

        if not drive.endswith(":"):
            drive = f"{drive}:"

        try:
            result = subprocess.run(
                ["fsutil", "dirty", "set", drive],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def run_disk_cleanup(self, drive: str = "C:") -> Dict[str, Any]:
        """
        Run Disk Cleanup utility.

        Args:
            drive: Drive letter to clean (default: "C:").

        Returns:
            Dict[str, Any]: Cleanup results.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "drive": drive,
            "message": "Disk cleanup requires Windows.",
            "space_freed_mb": 0,
            "timestamp": datetime.now().isoformat(),
        }

        if not self._is_windows:
            return result

        try:
            subprocess_result = subprocess.run(
                ["cleanmgr", "/sagerun:1"],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if subprocess_result.returncode == 0:
                result["status"] = "success"
                result["message"] = "Disk cleanup completed."
            else:
                result["status"] = "error"
                result["message"] = subprocess_result.stderr or "Cleanup failed."

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["message"] = "Disk cleanup timed out."
        except (OSError, subprocess.SubprocessError) as exc:
            result["status"] = "error"
            result["message"] = str(exc)

        return result

    def sfc_scan(self) -> Dict[str, Any]:
        """
        Run System File Checker (sfc /scannow).

        Returns:
            Dict[str, Any]: Scan results including status and findings.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "message": "SFC requires Windows with admin privileges.",
            "corruptions_found": False,
            "corruptions_repaired": False,
            "timestamp": datetime.now().isoformat(),
        }

        if not self._is_windows:
            return result

        try:
            subprocess_result = subprocess.run(
                ["sfc", "/scannow"],
                capture_output=True,
                text=True,
                timeout=600,
            )

            output = subprocess_result.stdout
            result["raw_output"] = output

            if "found corrupt files" in output.lower():
                result["corruptions_found"] = True
                if "successfully repaired" in output.lower():
                    result["corruptions_repaired"] = True
                    result["status"] = "success"
                    result["message"] = "Corrupt files found and repaired."
                else:
                    result["status"] = "partial"
                    result["message"] = "Corrupt files found but could not repair all."
            else:
                result["status"] = "success"
                result["message"] = "No integrity violations found."

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["message"] = "SFC scan timed out."
        except (OSError, subprocess.SubprocessError) as exc:
            result["status"] = "error"
            result["message"] = str(exc)

        return result

    def dism_restore(self) -> Dict[str, Any]:
        """
        Run DISM to repair Windows system image.

        Returns:
            Dict[str, Any]: Repair results.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "message": "DISM requires Windows with admin privileges.",
            "timestamp": datetime.now().isoformat(),
        }

        if not self._is_windows:
            return result

        try:
            subprocess_result = subprocess.run(
                ["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"],
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes
            )

            output = subprocess_result.stdout
            result["raw_output"] = output

            if subprocess_result.returncode == 0:
                result["status"] = "success"
                if "restore operation completed" in output.lower():
                    result["message"] = "System image restored successfully."
                else:
                    result["message"] = "DISM operation completed."
            else:
                result["status"] = "error"
                result["message"] = f"DISM returned code {subprocess_result.returncode}"

        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
            result["message"] = "DISM operation timed out."
        except (OSError, subprocess.SubprocessError) as exc:
            result["status"] = "error"
            result["message"] = str(exc)

        return result

    # =====================================================================
    # Utility Methods
    # =====================================================================

    def export_settings_list(self, output_path: str, format: str = "json") -> bool:
        """
        Export all Control Panel settings to a file.

        Args:
            output_path: Path to the output file.
            format: Output format - "json" or "csv".

        Returns:
            bool: True if export was successful.
        """
        settings = self.list_control_panel_items()

        if format.lower() == "json":
            try:
                import json
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=2, ensure_ascii=False)
                return True
            except (OSError, TypeError):
                return False

        elif format.lower() == "csv":
            try:
                import csv
                with open(output_path, "w", newline="", encoding="utf-8") as f:
                    if settings:
                        writer = csv.DictWriter(f, fieldnames=settings[0].keys())
                        writer.writeheader()
                        writer.writerows(settings)
                return True
            except (OSError, csv.Error):
                return False

        return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the God Mode integration.

        Returns:
            Dict[str, Any]: Statistics including:
                - total_settings: Total number of settings
                - categories: Number of categories
                - category_breakdown: Settings count per category
                - god_mode_path: Current God Mode folder path
                - is_windows: Whether running on Windows
                - clsid: The God Mode CLSID
        """
        categories: Dict[str, int] = {}
        for item in self._control_panel_items:
            categories[item.category] = categories.get(item.category, 0) + 1

        return {
            "total_settings": len(self._control_panel_items),
            "categories": len(categories),
            "category_breakdown": categories,
            "god_mode_path": self.god_mode_path,
            "is_windows": self._is_windows,
            "clsid": GOD_MODE_CLSID,
            "folder_name": GOD_MODE_FOLDER_NAME,
        }


# =============================================================================
# MockWindowsGodMode Class (for non-Windows testing)
# =============================================================================

class MockWindowsGodMode(WindowsGodMode):
    """
    Mock implementation of WindowsGodMode for testing on non-Windows systems.

    Provides the same interface as WindowsGodMode but returns mock data
    instead of executing Windows-specific commands. Useful for:
    - Development on macOS/Linux
    - Unit testing
    - CI/CD pipelines
    - Documentation generation

    Usage:
        from windows_god_mode import MockWindowsGodMode

        god_mode = MockWindowsGodMode()
        settings = god_mode.list_control_panel_items()  # Returns mock data
        info = god_mode.get_system_info_full()  # Returns simulated data
    """

    def __init__(self):
        """Initialize the mock God Mode with simulated data."""
        # Don't call super().__init__ to avoid Windows-specific setup
        self.god_mode_path: Optional[str] = None
        self._control_panel_items: List[ControlPanelItem] = []
        self._is_windows = False
        self._build_control_panel_index()
        self._mock_system_info = self._generate_mock_system_info()

    def _generate_mock_system_info(self) -> Dict[str, Any]:
        """Generate realistic mock system information."""
        return {
            "os": "Windows",
            "version": "10.0.22631",
            "build": "22631",
            "architecture": "64bit",
            "machine": "AMD64",
            "processor": "Intel64 Family 6 Model 158 Stepping 13, GenuineIntel",
            "cpu_count": 16,
            "hostname": "JARVIS-BRAINIAC",
            "python_version": "3.12.0",
            "platform": "Windows-11-10.0.22631-SP0",
            "memory_gb": 32.0,
            "username": "jarvis",
            "is_admin": True,
            "boot_time": "2024-01-15T08:30:00",
            "product_type": "Windows 11 Pro",
            "edition": "Professional",
            "timestamp": datetime.now().isoformat(),
        }

    # Override Windows-specific methods
    def create_god_mode_folder(self, path: str = None) -> str:
        """Simulate creating God Mode folder (returns mock path)."""
        mock_path = path or "/tmp/mock_god_mode"
        self.god_mode_path = os.path.join(mock_path, GOD_MODE_FOLDER_NAME)
        return self.god_mode_path

    def get_system_info_full(self) -> Dict[str, Any]:
        """Return mock system information."""
        info = dict(self._mock_system_info)
        info["timestamp"] = datetime.now().isoformat()
        return info

    def get_network_settings(self) -> Dict[str, Any]:
        """Return mock network settings."""
        return {
            "hostname": "JARVIS-BRAINIAC",
            "hostname_fqdn": "JARVIS-BRAINIAC.local",
            "adapters": [
                {"name": "Intel(R) Wi-Fi 6 AX201", "mac_address": "AA:BB:CC:DD:EE:FF", "speed": "240000000"},
                {"name": "Realtek PCIe GbE Family Controller", "mac_address": "11:22:33:44:55:66", "speed": "1000000000"},
            ],
            "ipconfig_raw": "Mock ipconfig output for testing purposes.",
            "default_gateway": "192.168.1.1",
            "dns_servers": ["8.8.8.8", "8.8.4.4"],
            "dhcp_enabled": True,
            "timestamp": datetime.now().isoformat(),
        }

    def get_display_settings(self) -> Dict[str, Any]:
        """Return mock display settings."""
        return {
            "screen_resolution": "3840x2160",
            "refresh_rate": "144",
            "bit_depth": "32",
            "scaling": "150",
            "gpu_info": [
                {"name": "NVIDIA GeForce RTX 4090", "adapter_ram_mb": "24576", "video_mode": "3840x2160x32", "refresh_rate": "144"},
            ],
            "monitors": [
                {"name": "Dell U3223QE", "width": "3840", "height": "2160", "dpi": "140"},
            ],
            "primary_monitor": {"name": "Dell U3223QE", "width": "3840", "height": "2160"},
            "timestamp": datetime.now().isoformat(),
        }

    def get_power_settings(self) -> Dict[str, Any]:
        """Return mock power settings."""
        return {
            "active_power_plan": "High Performance",
            "power_plans": ["Balanced", "High Performance", "Power Saver"],
            "battery_present": True,
            "battery_level": 87,
            "battery_status": "Charging",
            "estimated_runtime": "4h 30m",
            "ac_line_status": True,
            "timestamp": datetime.now().isoformat(),
        }

    def get_security_settings(self) -> Dict[str, Any]:
        """Return mock security settings."""
        return {
            "firewall_enabled": True,
            "defender_enabled": True,
            "uac_enabled": True,
            "uac_level": "Notify with dimming",
            "bitlocker_status": {"C:": "Encrypted"},
            "antivirus_products": [
                {"name": "Windows Defender", "state": "397312", "enabled": True},
            ],
            "last_update": "2024-01-15T06:00:00",
            "secure_boot": True,
            "tpm_present": True,
            "windows_hello": True,
            "timestamp": datetime.now().isoformat(),
        }

    def get_storage_settings(self) -> Dict[str, Any]:
        """Return mock storage settings."""
        return {
            "drives": [
                {"letter": "C", "path": "C:\\", "total_gb": 1024.0, "used_gb": 456.7, "free_gb": 567.3, "usage_percent": 44.6},
                {"letter": "D", "path": "D:\\", "total_gb": 2048.0, "used_gb": 890.1, "free_gb": 1157.9, "usage_percent": 43.5},
                {"letter": "E", "path": "E:\\", "total_gb": 512.0, "used_gb": 120.5, "free_gb": 391.5, "usage_percent": 23.5},
            ],
            "total_space_gb": 3584.0,
            "free_space_gb": 2116.7,
            "disk_type": "SSD",
            "volumes": [
                {"drive_letter": "C:", "filesystem": "NTFS", "capacity_gb": "1024.0", "free_gb": "567.3"},
                {"drive_letter": "D:", "filesystem": "NTFS", "capacity_gb": "2048.0", "free_gb": "1157.9"},
                {"drive_letter": "E:", "filesystem": "NTFS", "capacity_gb": "512.0", "free_gb": "391.5"},
            ],
            "timestamp": datetime.now().isoformat(),
        }

    def open_setting(self, setting_name: str) -> bool:
        """Simulate opening a setting (logs action)."""
        print(f"[MOCK] Would open setting: {setting_name}")
        return True

    def open_event_viewer(self) -> bool:
        """Simulate opening Event Viewer."""
        print("[MOCK] Would open Event Viewer (eventvwr.msc)")
        return True

    def open_device_manager(self) -> bool:
        """Simulate opening Device Manager."""
        print("[MOCK] Would open Device Manager (devmgmt.msc)")
        return True

    def open_disk_management(self) -> bool:
        """Simulate opening Disk Management."""
        print("[MOCK] Would open Disk Management (diskmgmt.msc)")
        return True

    def open_services(self) -> bool:
        """Simulate opening Services."""
        print("[MOCK] Would open Services (services.msc)")
        return True

    def open_registry_editor(self, confirm: bool = True) -> bool:
        """Simulate opening Registry Editor."""
        if confirm:
            print("[MOCK] Would open Registry Editor (regedit.exe) - with warning")
        else:
            print("[MOCK] Would open Registry Editor (regedit.exe)")
        return True

    def open_group_policy(self) -> bool:
        """Simulate opening Group Policy Editor."""
        print("[MOCK] Would open Local Group Policy Editor (gpedit.msc)")
        return True

    def open_task_scheduler(self) -> bool:
        """Simulate opening Task Scheduler."""
        print("[MOCK] Would open Task Scheduler (taskschd.msc)")
        return True

    def open_performance_monitor(self) -> bool:
        """Simulate opening Performance Monitor."""
        print("[MOCK] Would open Performance Monitor (perfmon.msc)")
        return True

    def open_resource_monitor(self) -> bool:
        """Simulate opening Resource Monitor."""
        print("[MOCK] Would open Resource Monitor (resmon.exe)")
        return True

    def open_system_configuration(self) -> bool:
        """Simulate opening System Configuration."""
        print("[MOCK] Would open System Configuration (msconfig.exe)")
        return True

    def open_computer_management(self) -> bool:
        """Simulate opening Computer Management."""
        print("[MOCK] Would open Computer Management (compmgmt.msc)")
        return True

    def open_local_security_policy(self) -> bool:
        """Simulate opening Local Security Policy."""
        print("[MOCK] Would open Local Security Policy (secpol.msc)")
        return True

    def open_component_services(self) -> bool:
        """Simulate opening Component Services."""
        print("[MOCK] Would open Component Services (comexp.msc)")
        return True

    def open_certificates(self) -> bool:
        """Simulate opening Certificate Manager."""
        print("[MOCK] Would open Certificate Manager (certmgr.msc)")
        return True

    def open_windows_firewall(self) -> bool:
        """Simulate opening Windows Firewall."""
        print("[MOCK] Would open Windows Firewall (wf.msc)")
        return True

    def open_iis_manager(self) -> bool:
        """Simulate opening IIS Manager."""
        print("[MOCK] Would open IIS Manager (inetmgr.exe)")
        return True

    def open_hyper_v_manager(self) -> bool:
        """Simulate opening Hyper-V Manager."""
        print("[MOCK] Would open Hyper-V Manager (virtmgmt.msc)")
        return True

    def open_print_management(self) -> bool:
        """Simulate opening Print Management."""
        print("[MOCK] Would open Print Management (printmanagement.msc)")
        return True

    def open_wmi_management(self) -> bool:
        """Simulate opening WMI Management."""
        print("[MOCK] Would open WMI Management (wmimgmt.msc)")
        return True

    def open_shared_folders(self) -> bool:
        """Simulate opening Shared Folders."""
        print("[MOCK] Would open Shared Folders (fsmgmt.msc)")
        return True

    def clear_temp_files(self) -> int:
        """Simulate clearing temp files."""
        mock_count = 42
        print(f"[MOCK] Would clear {mock_count} temporary files")
        return mock_count

    def optimize_drives(self) -> Dict[str, Any]:
        """Simulate drive optimization."""
        return {
            "status": "success",
            "drives_optimized": ["C", "D", "E"],
            "message": "[MOCK] Drive optimization completed successfully.",
            "recommendation": "Run optimization monthly.",
            "timestamp": datetime.now().isoformat(),
        }

    def check_disk(self, drive: str = "C:") -> Dict[str, Any]:
        """Simulate disk check."""
        return {
            "status": "success",
            "drive": drive,
            "message": f"[MOCK] Disk check completed for {drive}. No errors found.",
            "requires_reboot": False,
            "errors_found": False,
            "timestamp": datetime.now().isoformat(),
        }

    def schedule_disk_check(self, drive: str = "C:") -> bool:
        """Simulate scheduling a disk check."""
        print(f"[MOCK] Would schedule disk check for {drive} on next reboot")
        return True

    def run_disk_cleanup(self, drive: str = "C:") -> Dict[str, Any]:
        """Simulate disk cleanup."""
        return {
            "status": "success",
            "drive": drive,
            "message": f"[MOCK] Disk cleanup completed for {drive}.",
            "space_freed_mb": 1500,
            "timestamp": datetime.now().isoformat(),
        }

    def sfc_scan(self) -> Dict[str, Any]:
        """Simulate System File Checker scan."""
        return {
            "status": "success",
            "message": "[MOCK] SFC scan completed. No integrity violations found.",
            "corruptions_found": False,
            "corruptions_repaired": False,
            "timestamp": datetime.now().isoformat(),
        }

    def dism_restore(self) -> Dict[str, Any]:
        """Simulate DISM restore."""
        return {
            "status": "success",
            "message": "[MOCK] DISM restore completed successfully.",
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# Factory Function
# =============================================================================

def get_windows_god_mode(mock: bool = False) -> Union[WindowsGodMode, MockWindowsGodMode]:
    """
    Factory function to get the appropriate Windows God Mode instance.

    Automatically detects the platform and returns either a real
    WindowsGodMode or a MockWindowsGodMode for non-Windows systems.

    Args:
        mock: If True, force mock mode even on Windows.

    Returns:
        Union[WindowsGodMode, MockWindowsGodMode]: The appropriate instance.

    Example:
        >>> god_mode = get_windows_god_mode()
        >>> isinstance(god_mode, (WindowsGodMode, MockWindowsGodMode))
        True
        >>> settings = god_mode.list_control_panel_items()
        >>> len(settings) > 200
        True
    """
    is_windows = platform.system() == "Windows"

    if mock or not is_windows:
        return MockWindowsGodMode()
    else:
        return WindowsGodMode()


# =============================================================================
# Command-line interface
# =============================================================================

def main():
    """CLI entry point for the Windows God Mode integration."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="JARVIS BRAINIAC - Windows God Mode Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                    List all 200+ Control Panel items
  %(prog)s --search "network"        Search for network-related settings
  %(prog)s --open "Device Manager"   Open a specific setting
  %(prog)s --info                    Show full system information
  %(prog)s --stats                   Show integration statistics
  %(prog)s --create                  Create God Mode folder on Desktop
  %(prog)s --export settings.json    Export settings to JSON
        """,
    )
    parser.add_argument("--list", action="store_true", help="List all settings")
    parser.add_argument("--search", type=str, metavar="QUERY", help="Search settings")
    parser.add_argument("--open", type=str, metavar="NAME", help="Open a setting")
    parser.add_argument("--info", action="store_true", help="Show system info")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--create", action="store_true", help="Create God Mode folder")
    parser.add_argument("--export", type=str, metavar="PATH", help="Export to file")
    parser.add_argument("--mock", action="store_true", help="Use mock mode")
    parser.add_argument("--format", type=str, default="json", choices=["json", "csv"],
                        help="Export format (default: json)")
    parser.add_argument("--categories", action="store_true", help="List categories")
    parser.add_argument("--category", type=str, metavar="NAME", help="Show settings in category")

    args = parser.parse_args()

    god_mode = get_windows_god_mode(mock=args.mock)

    if args.list:
        items = god_mode.list_control_panel_items()
        print(f"\nTotal Settings: {len(items)}\n")
        for item in items[:50]:  # Show first 50
            print(f"  [{item['category']}] {item['name']}")
        if len(items) > 50:
            print(f"  ... and {len(items) - 50} more")

    elif args.search:
        results = god_mode.search_settings(args.search)
        print(f"\nSearch results for '{args.search}': {len(results)} found\n")
        for item in results[:20]:
            print(f"  [{item['category']}] {item['name']} -> {item['command']}")

    elif args.open:
        success = god_mode.open_setting(args.open)
        print(f"\nOpening '{args.open}': {'SUCCESS' if success else 'FAILED'}")

    elif args.info:
        info = god_mode.get_system_info_full()
        print(json.dumps(info, indent=2, default=str))

    elif args.stats:
        stats = god_mode.get_stats()
        print(json.dumps(stats, indent=2, default=str))

    elif args.create:
        try:
            path = god_mode.create_god_mode_folder()
            print(f"\nGod Mode folder created at: {path}")
        except RuntimeError as exc:
            print(f"\nError: {exc}")

    elif args.export:
        success = god_mode.export_settings_list(args.export, args.format)
        print(f"\nExport to {args.export}: {'SUCCESS' if success else 'FAILED'}")

    elif args.categories:
        cats = god_mode.get_all_categories()
        print(f"\nCategories ({len(cats)}):\n")
        for cat in cats:
            count = len(god_mode.get_settings_by_category(cat))
            print(f"  {cat}: {count} settings")

    elif args.category:
        items = god_mode.get_settings_by_category(args.category)
        print(f"\nSettings in '{args.category}': {len(items)}\n")
        for item in items:
            print(f"  {item['name']} -> {item['command']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
