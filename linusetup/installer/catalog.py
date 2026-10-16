"""Static choices offered by the installer. Pure data; every package, keymap and
layout name here is checked against the real repos / kbd / xkb by the tests."""
from pathlib import Path

# --------------------------------------------------------------------------
# Keyboard layouts: id -> (label, console keymap, xkb layout, xkb variant, xkb options)
# Non-Latin layouts keep a Latin console keymap (so a LUKS passphrase can always
# be typed at boot) and get "us" as a second X/Wayland layout with Alt+Shift.
TOGGLE = "grp:alt_shift_toggle"
KEYBOARDS = {
    "us":       ("English (US)", "us", "us", "", ""),
    "us-intl":  ("English (US, international)", "us-acentos", "us", "intl", ""),
    "uk":       ("English (UK)", "uk", "gb", "", ""),
    "dvorak":   ("English (Dvorak)", "dvorak", "us", "dvorak", ""),
    "colemak":  ("English (Colemak)", "colemak", "us", "colemak", ""),
    "de":       ("German", "de-latin1", "de", "", ""),
    "de-ch":    ("German (Switzerland)", "de_CH-latin1", "ch", "", ""),
    "fr":       ("French", "fr-latin1", "fr", "", ""),
    "fr-ch":    ("French (Switzerland)", "fr_CH-latin1", "ch", "fr", ""),
    "fr-ca":    ("French (Canada)", "cf", "ca", "", ""),
    "be":       ("Belgian", "be-latin1", "be", "", ""),
    "es":       ("Spanish", "es", "es", "", ""),
    "latam":    ("Spanish (Latin America)", "la-latin1", "latam", "", ""),
    "pt":       ("Portuguese", "pt-latin1", "pt", "", ""),
    "br":       ("Portuguese (Brazil)", "br-abnt2", "br", "", ""),
    "it":       ("Italian", "it", "it", "", ""),
    "nl":       ("Dutch", "nl", "nl", "", ""),
    "se":       ("Swedish", "sv-latin1", "se", "", ""),
    "no":       ("Norwegian", "no-latin1", "no", "", ""),
    "dk":       ("Danish", "dk-latin1", "dk", "", ""),
    "fi":       ("Finnish", "fi", "fi", "", ""),
    "pl":       ("Polish", "pl2", "pl", "", ""),
    "cz":       ("Czech", "cz-qwertz", "cz", "", ""),
    "sk":       ("Slovak", "sk-qwertz", "sk", "", ""),
    "hu":       ("Hungarian", "hu", "hu", "", ""),
    "ro":       ("Romanian", "ro", "ro", "", ""),
    "tr":       ("Turkish", "trq", "tr", "", ""),
    "jp":       ("Japanese", "jp106", "jp", "", ""),
    "gr":       ("Greek", "us", "us,gr", "", TOGGLE),
    "ru":       ("Russian", "us", "us,ru", "", TOGGLE),
    "ua":       ("Ukrainian", "us", "us,ua", "", TOGGLE),
    "ara":      ("Arabic", "us", "us,ara", "", TOGGLE),
    "il":       ("Hebrew", "us", "us,il", "", TOGGLE),
    "ir":       ("Persian", "us", "us,ir", "", TOGGLE),
    "th":       ("Thai", "us", "us,th", "", TOGGLE),
    "kr":       ("Korean", "us", "kr", "", ""),
}

# --------------------------------------------------------------------------
# Mirror countries accepted by `reflector --country` (codes; from reflector --list-countries)
COUNTRIES = dict(c.split("|") for c in (
    "AL|Albania;AR|Argentina;AM|Armenia;AU|Australia;AT|Austria;AZ|Azerbaijan;BD|Bangladesh;"
    "BY|Belarus;BE|Belgium;BR|Brazil;BG|Bulgaria;KH|Cambodia;CA|Canada;CL|Chile;CN|China;"
    "CO|Colombia;HR|Croatia;CZ|Czechia;DK|Denmark;EC|Ecuador;EE|Estonia;FI|Finland;FR|France;"
    "GE|Georgia;DE|Germany;GR|Greece;HK|Hong Kong;HU|Hungary;IS|Iceland;IN|India;ID|Indonesia;"
    "IR|Iran;IL|Israel;IT|Italy;JP|Japan;KZ|Kazakhstan;KE|Kenya;LV|Latvia;LT|Lithuania;"
    "LU|Luxembourg;MY|Malaysia;MX|Mexico;MD|Moldova;MA|Morocco;NP|Nepal;NL|Netherlands;"
    "NC|New Caledonia;NZ|New Zealand;MK|North Macedonia;NO|Norway;PY|Paraguay;PH|Philippines;"
    "PL|Poland;PT|Portugal;RO|Romania;RU|Russia;RE|Réunion;SA|Saudi Arabia;RS|Serbia;"
    "SG|Singapore;SK|Slovakia;SI|Slovenia;ZA|South Africa;KR|South Korea;ES|Spain;SE|Sweden;"
    "CH|Switzerland;TW|Taiwan;TH|Thailand;TN|Tunisia;TR|Türkiye;UA|Ukraine;"
    "AE|United Arab Emirates;GB|United Kingdom;US|United States;UZ|Uzbekistan;VN|Vietnam"
).split(";"))

# --------------------------------------------------------------------------
KERNELS = {
    "linux": ("Linux", "The latest stable kernel. Best for most people."),
    "linux-lts": ("Linux LTS", "Long-term support. Slower changes, very stable."),
    "linux-zen": ("Linux Zen", "Tuned for desktop responsiveness and gaming."),
    "linux-hardened": ("Linux Hardened", "Security-focused. Some apps may not work."),
}

FILESYSTEMS = {
    "ext4": ("ext4", "Proven and simple. The safe default."),
    "btrfs": ("Btrfs", "Snapshots, compression and subvolumes."),
    "xfs": ("XFS", "Fast with large files. Cannot be shrunk later."),
    "f2fs": ("F2FS", "Designed for flash storage. No swap file support."),
}
FS_PACKAGES = {"ext4": ("e2fsprogs",), "btrfs": ("btrfs-progs",), "xfs": ("xfsprogs",),
               "f2fs": ("f2fs-tools",), "vfat": ("dosfstools",), "ntfs": ("ntfs-3g",)}

# --------------------------------------------------------------------------
# Desktop profiles. kind: desktop | wm | other.  x11: needs an X server.
# skel: (source inside the new system, destination under /etc/skel) copied
# before users are created, for WMs that ship no usable default config.
PROFILES = {
    "kde": dict(name="KDE Plasma", kind="desktop", greeter="sddm", x11=False,
                blurb="Modern, polished and endlessly customisable.",
                packages=("plasma-desktop", "plasma-nm", "plasma-pa", "kscreen", "powerdevil",
                          "bluedevil", "kde-gtk-config", "breeze-gtk", "xdg-desktop-portal-kde",
                          "plasma-systemmonitor", "kinfocenter", "kwallet-pam", "sddm-kcm",
                          "konsole", "dolphin", "kate", "ark", "spectacle", "gwenview", "okular",
                          "power-profiles-daemon")),
    "gnome": dict(name="GNOME", kind="desktop", greeter="gdm", x11=False,
                  blurb="Clean and focused, with a workflow of its own.",
                  packages=("gnome", "gnome-tweaks")),
    "cinnamon": dict(name="Cinnamon", kind="desktop", greeter="lightdm", x11=True,
                     blurb="Traditional and familiar, like Windows.",
                     packages=("cinnamon", "gnome-terminal", "xed", "network-manager-applet")),
    "xfce": dict(name="Xfce", kind="desktop", greeter="lightdm", x11=True,
                 blurb="Lightweight and reliable, great on older hardware.",
                 packages=("xfce4", "xfce4-goodies", "pavucontrol", "network-manager-applet")),
    "cosmic": dict(name="COSMIC", kind="desktop", greeter="cosmic-greeter", x11=False,
                   blurb="System76's new Rust desktop with tiling built in.",
                   packages=("cosmic",)),
    "mate": dict(name="MATE", kind="desktop", greeter="lightdm", x11=True,
                 blurb="The classic GNOME 2 experience.",
                 packages=("mate", "mate-extra", "network-manager-applet")),
    "lxqt": dict(name="LXQt", kind="desktop", greeter="sddm", x11=True,
                 blurb="Very light Qt desktop.",
                 packages=("lxqt", "breeze-icons", "network-manager-applet")),
    "budgie": dict(name="Budgie", kind="desktop", greeter="lightdm", x11=True,
                   blurb="Simple and elegant.",
                   packages=("budgie-desktop", "gnome-terminal", "nemo", "network-manager-applet")),
    "hyprland": dict(name="Hyprland", kind="wm", greeter="sddm", x11=False,
                     blurb="Animated dynamic tiling on Wayland.",
                     packages=("hyprland", "kitty", "waybar", "wofi", "dunst",
                               "xdg-desktop-portal-hyprland", "hyprpolkitagent", "dolphin",
                               "grim", "slurp", "wl-clipboard", "brightnessctl")),
    "sway": dict(name="Sway", kind="wm", greeter="sddm", x11=False,
                 blurb="i3-compatible tiling on Wayland.",
                 packages=("sway", "swaybg", "swayidle", "swaylock", "waybar", "foot", "wofi",
                           "mako", "xdg-desktop-portal-wlr", "grim", "slurp", "wl-clipboard",
                           "brightnessctl")),
    "i3": dict(name="i3", kind="wm", greeter="lightdm", x11=True,
               blurb="The classic keyboard-driven tiling WM.",
               packages=("i3-wm", "i3status", "i3lock", "xss-lock", "dmenu", "alacritty",
                         "dunst", "feh", "network-manager-applet")),
    "bspwm": dict(name="bspwm", kind="wm", greeter="lightdm", x11=True,
                  blurb="Binary space partitioning, configured by scripts.",
                  packages=("bspwm", "sxhkd", "alacritty", "rofi", "polybar", "dunst", "feh"),
                  skel=(("/usr/share/doc/bspwm/examples/bspwmrc", ".config/bspwm/bspwmrc", 0o755),
                        ("/usr/share/doc/bspwm/examples/sxhkdrc", ".config/sxhkd/sxhkdrc", 0o644))),
    "awesome": dict(name="awesome", kind="wm", greeter="lightdm", x11=True,
                    blurb="Highly configurable framework WM in Lua.",
                    packages=("awesome", "alacritty", "rofi", "dunst")),
    "qtile": dict(name="Qtile", kind="wm", greeter="lightdm", x11=True,
                  blurb="A tiling WM written and configured in Python.",
                  packages=("qtile", "alacritty", "rofi", "dunst")),
    "openbox": dict(name="Openbox", kind="wm", greeter="lightdm", x11=True,
                    blurb="Minimal floating WM with a right-click menu.",
                    packages=("openbox", "obconf-qt", "tint2", "alacritty", "rofi", "feh")),
    "server": dict(name="Server (TTY + SSH)", kind="other", greeter="none", x11=False,
                   blurb="Boots to a text console with an SSH server. No graphical desktop.",
                   packages=("openssh",), services=("sshd",)),
    "minimal": dict(name="No desktop (TTY only)", kind="other", greeter="none", x11=False,
                    blurb="Boots to a text console. No graphical desktop at all.",
                    packages=()),
}

GREETERS = {
    "sddm": ("SDDM", ("sddm",), "sddm"),
    "gdm": ("GDM", ("gdm",), "gdm"),
    "lightdm": ("LightDM", ("lightdm", "lightdm-gtk-greeter"), "lightdm"),
    "cosmic-greeter": ("COSMIC Greeter", ("cosmic-greeter",), "cosmic-greeter"),
    "none": ("None (log in on the console)", (), None),
}

# --------------------------------------------------------------------------
GRAPHICS = {
    "auto": "Detect automatically",
    "nvidia-open": "NVIDIA (open kernel modules, GTX 16xx / RTX and newer)",
    "nouveau": "NVIDIA (nouveau, open source, older cards)",
    "amd": "AMD / ATI",
    "intel": "Intel",
    "vm": "Virtual machine",
    "mesa": "Generic (Mesa only)",
}
# driver -> (packages, 32-bit packages added when multilib is used)
GRAPHICS_PACKAGES = {
    "nvidia-open": (("nvidia-utils", "nvidia-settings"), ("lib32-nvidia-utils",)),
    "nouveau": (("mesa", "vulkan-nouveau"), ("lib32-mesa", "lib32-vulkan-nouveau")),
    "amd": (("mesa", "vulkan-radeon"), ("lib32-mesa", "lib32-vulkan-radeon")),
    "intel": (("mesa", "vulkan-intel", "intel-media-driver"), ("lib32-mesa", "lib32-vulkan-intel")),
    "vm": (("mesa",), ("lib32-mesa", "lib32-vulkan-swrast")),
    "mesa": (("mesa",), ("lib32-mesa", "lib32-vulkan-swrast")),
}
# systemd-detect-virt id -> (packages, services)
VM_TOOLS = {
    "kvm": (("qemu-guest-agent", "spice-vdagent"), ()),
    "qemu": (("qemu-guest-agent", "spice-vdagent"), ()),
    "oracle": (("virtualbox-guest-utils",), ("vboxservice",)),
    "vmware": (("open-vm-tools",), ("vmtoolsd", "vmware-vmblock-fuse")),
}

AUDIO = {
    "pipewire": ("PipeWire (recommended)",
                 ("pipewire", "pipewire-alsa", "pipewire-pulse", "pipewire-jack", "wireplumber",
                  "sof-firmware", "alsa-utils")),
    "none": ("No sound server", ()),
}

NETWORK = {
    "networkmanager": ("NetworkManager (recommended)", ("networkmanager",), ("NetworkManager",)),
    "networkd": ("systemd-networkd + iwd (minimal)", ("iwd",),
                 ("systemd-networkd", "systemd-resolved", "iwd")),
    "none": ("Nothing (configure it yourself)", (), ()),
}

FIREWALLS = {
    "none": ("No firewall", (), ()),
    "ufw": ("ufw (simple)", ("ufw",), ("ufw",)),
    "firewalld": ("firewalld (zones)", ("firewalld",), ("firewalld",)),
}

SHELLS = {"bash": ("/bin/bash", ()), "zsh": ("/usr/bin/zsh", ("zsh", "zsh-completions")),
          "fish": ("/usr/bin/fish", ("fish",))}

AUR_HELPERS = {"none": "None", "yay": "yay", "paru": "paru"}

# --------------------------------------------------------------------------
# Software catalog: category -> items. Every item is an optional bundle.
# needs_multilib marks 32-bit dependencies (Steam etc.).
SOFTWARE = [
    ("Web & communication", [
        dict(id="firefox", name="Firefox", desc="Fast, private web browser", packages=("firefox",)),
        dict(id="chromium", name="Chromium", desc="Open-source base of Chrome", packages=("chromium",)),
        dict(id="thunderbird", name="Thunderbird", desc="Email and calendar", packages=("thunderbird",)),
        dict(id="telegram", name="Telegram", desc="Messaging", packages=("telegram-desktop",)),
        dict(id="discord", name="Discord", desc="Voice and chat", packages=("discord",)),
        dict(id="qbittorrent", name="qBittorrent", desc="Torrent client", packages=("qbittorrent",)),
    ]),
    ("Office & productivity", [
        dict(id="libreoffice", name="LibreOffice", desc="Documents, spreadsheets, slides", packages=("libreoffice-fresh",)),
        dict(id="obsidian", name="Obsidian", desc="Markdown notes", packages=("obsidian",)),
        dict(id="keepassxc", name="KeePassXC", desc="Offline password manager", packages=("keepassxc",)),
        dict(id="syncthing", name="Syncthing", desc="Sync files between devices", packages=("syncthing",)),
    ]),
    ("Media & creative", [
        dict(id="vlc", name="VLC", desc="Plays everything", packages=("vlc",)),
        dict(id="mpv", name="mpv", desc="Minimal video player", packages=("mpv",)),
        dict(id="codecs", name="Extra codecs", desc="GStreamer plugins and FFmpeg", packages=("ffmpeg", "gst-plugins-good", "gst-plugins-bad", "gst-plugins-ugly", "gst-libav")),
        dict(id="gimp", name="GIMP", desc="Photo editing", packages=("gimp",)),
        dict(id="krita", name="Krita", desc="Digital painting", packages=("krita",)),
        dict(id="inkscape", name="Inkscape", desc="Vector graphics", packages=("inkscape",)),
        dict(id="blender", name="Blender", desc="3D creation suite", packages=("blender",)),
        dict(id="kdenlive", name="Kdenlive", desc="Video editing", packages=("kdenlive",)),
        dict(id="obs", name="OBS Studio", desc="Streaming and recording", packages=("obs-studio",)),
        dict(id="audacity", name="Audacity", desc="Audio editing", packages=("audacity",)),
    ]),
    ("Gaming", [
        dict(id="steam", name="Steam", desc="Steam with Proton for Windows games", packages=("steam",), needs_multilib=True),
        dict(id="lutris", name="Lutris", desc="One launcher for every game store", packages=("lutris",)),
        dict(id="wine", name="Wine", desc="Run Windows apps", packages=("wine", "wine-mono", "wine-gecko", "winetricks"), needs_multilib=True),
        dict(id="gamemode", name="GameMode", desc="Performance tweaks while gaming", packages=("gamemode", "lib32-gamemode"), needs_multilib=True),
        dict(id="mangohud", name="MangoHud", desc="FPS and temperature overlay", packages=("mangohud", "lib32-mangohud"), needs_multilib=True),
        dict(id="gamescope", name="Gamescope", desc="Valve's gaming compositor", packages=("gamescope",)),
        dict(id="prismlauncher", name="Prism Launcher", desc="Minecraft launcher", packages=("prismlauncher",)),
    ]),
    ("Development", [
        dict(id="devtools", name="Build tools", desc="base-devel and Git", packages=("base-devel", "git")),
        dict(id="vscode", name="Code - OSS", desc="Visual Studio Code, open source build", packages=("code",)),
        dict(id="neovim", name="Neovim", desc="Hyperextensible Vim", packages=("neovim",)),
        dict(id="docker", name="Docker", desc="Containers (+ compose)", packages=("docker", "docker-compose"), services=("docker",), groups=("docker",)),
        dict(id="podman", name="Podman", desc="Daemonless containers", packages=("podman",)),
        dict(id="distrobox", name="Distrobox", desc="Any distro in a container", packages=("distrobox", "podman")),
        dict(id="python", name="Python tools", desc="pip and pipx", packages=("python-pip", "python-pipx")),
        dict(id="node", name="Node.js", desc="Node and npm", packages=("nodejs", "npm")),
        dict(id="rust", name="Rust", desc="rustup toolchain manager", packages=("rustup",)),
        dict(id="go", name="Go", desc="The Go toolchain", packages=("go",)),
        dict(id="java", name="Java", desc="OpenJDK", packages=("jdk-openjdk",)),
    ]),
    ("System & terminal", [
        dict(id="cli", name="Terminal essentials", desc="htop, btop, fastfetch, ripgrep, fd, bat, eza, tmux", packages=("htop", "btop", "fastfetch", "ripgrep", "fd", "bat", "eza", "tmux")),
        dict(id="archive", name="Archive tools", desc="zip, unzip, 7-Zip", packages=("zip", "unzip", "7zip")),
        dict(id="filesystems", name="Other filesystems", desc="NTFS, exFAT, FAT support", packages=("ntfs-3g", "exfatprogs", "dosfstools")),
        dict(id="fonts", name="Extra fonts", desc="CJK, more scripts, Liberation, JetBrains Mono", packages=("noto-fonts-cjk", "noto-fonts-extra", "ttf-liberation", "ttf-jetbrains-mono")),
        dict(id="fwupd", name="Firmware updates", desc="fwupd for BIOS and device firmware", packages=("fwupd",)),
        dict(id="vpn", name="VPN tools", desc="WireGuard and OpenVPN", packages=("wireguard-tools", "openvpn")),
    ]),
]

SOFTWARE_INDEX = {item["id"]: item for _, items in SOFTWARE for item in items}

# Always part of a graphical install.
DESKTOP_BASE = ("xdg-user-dirs", "xdg-utils", "noto-fonts", "noto-fonts-emoji", "ttf-dejavu")
BASE = ("base", "linux-firmware", "sudo", "nano", "vim", "man-db", "man-pages",
        "bash-completion", "less", "which")


def locales():
    """UTF-8 locales from glibc's list, or a short fallback outside Arch."""
    path = Path("/usr/share/i18n/SUPPORTED")
    try:
        out = [l.split()[0] for l in path.read_text().splitlines()
               if l.endswith(" UTF-8") and ".UTF-8" in l.split()[0]]
        if out:
            return out
    except OSError:
        pass
    return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8", "es_ES.UTF-8",
            "ar_EG.UTF-8", "ja_JP.UTF-8"]


def for_ui():
    """Everything the UI needs to render choices."""
    return dict(
        keyboards=[dict(id=k, label=v[0]) for k, v in KEYBOARDS.items()],
        countries=[dict(id=k, label=v) for k, v in sorted(COUNTRIES.items(), key=lambda x: x[1])],
        kernels=[dict(id=k, label=v[0], desc=v[1]) for k, v in KERNELS.items()],
        filesystems=[dict(id=k, label=v[0], desc=v[1]) for k, v in FILESYSTEMS.items()],
        profiles=[dict(id=k, name=v["name"], kind=v["kind"], blurb=v["blurb"],
                       greeter=v["greeter"], packages=list(v["packages"]))
                  for k, v in PROFILES.items()],
        greeters=[dict(id=k, label=v[0]) for k, v in GREETERS.items()],
        graphics=[dict(id=k, label=v) for k, v in GRAPHICS.items()],
        audio=[dict(id=k, label=v[0]) for k, v in AUDIO.items()],
        network=[dict(id=k, label=v[0]) for k, v in NETWORK.items()],
        firewalls=[dict(id=k, label=v[0]) for k, v in FIREWALLS.items()],
        shells=list(SHELLS),
        aur_helpers=[dict(id=k, label=v) for k, v in AUR_HELPERS.items()],
        software=[dict(category=c, items=[dict(i, packages=list(i["packages"])) for i in items])
                  for c, items in SOFTWARE],
        locales=locales(),
    )
