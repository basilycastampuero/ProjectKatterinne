"""Nombres legibles de aplicaciones a partir del ejecutable.

Logica pura, sin Windows de por medio: entra `"Code.exe"`, sale
`"Visual Studio Code"`. Se puede testear en cualquier plataforma.

No se usa el LLM para esto. Convertir un nombre de ejecutable en un nombre de
aplicacion es una tabla, no un problema de lenguaje (CLAUDE.md seccion 3.4).
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
}

#: Cuando ni siquiera se conoce el ejecutable (proceso protegido, por ejemplo).
UNKNOWN_APPLICATION = "Desconocida"


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
