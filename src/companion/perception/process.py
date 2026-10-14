"""Nombres legibles de aplicaciones a partir del ejecutable.

Logica pura, sin Windows de por medio: entra `"Code.exe"`, sale
`"Visual Studio Code"`. Se puede testear en cualquier plataforma.

No se usa el LLM para esto. Convertir un nombre de ejecutable en un nombre de
aplicacion es una tabla, no un problema de lenguaje.
"""

from __future__ import annotations

#: Ejecutables cuyo nombre no se parece al de la aplicacion.
#:
#: Es una lista corta a proposito. Solo entran aqui los casos donde el
#: ejecutable induce a error ("Code.exe" no dice nada de VS Code). Para todo
#: lo demas, quitar la extension da un resultado perfectamente decente y no
#: hay que mantener nada.
KNOWN_APPLICATIONS: dict[str, str] = {
    "code.exe": "Visual Studio Code",
    "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA",
    "pycharm64.exe": "PyCharm",
    "msedge.exe": "Microsoft Edge",
    "chrome.exe": "Google Chrome",
    "firefox.exe": "Mozilla Firefox",
    "explorer.exe": "Explorador de Windows",
    "windowsterminal.exe": "Windows Terminal",
    "pwsh.exe": "PowerShell",
    "powershell.exe": "Windows PowerShell",
    "cmd.exe": "Simbolo del sistema",
    "notepad.exe": "Bloc de notas",
    "whatsapp.root.exe": "WhatsApp",
    # Los que más salían con nombre feo en una memoria real.
    "taskmgr.exe": "Administrador de tareas",
    "valorant-win64-shipping.exe": "VALORANT",
    "epicgameslauncher.exe": "Epic Games Launcher",
    "snippingtool.exe": "Recortes",
    "nvcplui.exe": "Panel de control de NVIDIA",
}

#: Partes del propio Windows que se ponen delante un momento: el buscador,
#: el menú Inicio, los paneles de la barra de tareas, las notificaciones,
#: la pantalla de bloqueo, el diálogo "Abrir con". No son estar en una
#: aplicación: abrir Inicio dos segundos no debe cortar lo que se estaba
#: haciendo. Se ignoran siempre, igual que el terminal en
#: `ignore_processes`, pero no van en esa lista porque no dependen de desde
#: dónde se ejecute la compañera. Salieron, por este orden, en la memoria
#: real: SearchHost 27 veces, ShellHost 15, ShellExperienceHost 12...
#: Claves normalizadas.
WINDOWS_SHELL_PROCESSES: frozenset[str] = frozenset(
    {
        "searchhost",
        "shellhost",
        "shellexperiencehost",
        "lockapp",
        "startmenuexperiencehost",
        "openwith",
    }
)

#: Cuando ni siquiera se conoce el ejecutable (proceso protegido, por ejemplo).
UNKNOWN_APPLICATION = "Desconocida"


def normalize_process(name: str) -> str:
    """Normaliza un nombre de proceso para poder compararlo.

    Windows no distingue mayusculas en nombres de fichero, y a nadie le
    apetece recordar si escribio la extension. Estas tres formas son la misma
    cosa para cualquier tabla o lista del sistema:

    >>> normalize_process("1Password.exe")
    '1password'
    >>> normalize_process("1password")
    '1password'
    >>> normalize_process("  1PASSWORD.EXE  ")
    '1password'
    """
    cleaned = name.strip().lower()
    return cleaned[:-4] if cleaned.endswith(".exe") else cleaned


def application_name(process_name: str) -> str:
    """Nombre legible de la aplicacion dueña de un ejecutable.

    >>> application_name("Code.exe")
    'Visual Studio Code'
    >>> application_name("obsidian.exe")
    'Obsidian'
    >>> application_name("")
    'Desconocida'
    """
    if not process_name:
        return UNKNOWN_APPLICATION

    key = process_name.lower()
    if known := KNOWN_APPLICATIONS.get(key):
        return known

    stem = process_name[:-4] if key.endswith(".exe") else process_name
    if not stem:
        return UNKNOWN_APPLICATION
    # Solo se toca la primera letra: `.title()` destrozaria nombres como
    # "obsidian" -> "Obsidian" bien, pero "iTunes" -> "Itunes" mal.
    return stem[0].upper() + stem[1:]
