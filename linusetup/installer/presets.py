"""What gets installed. Pure data, no side effects."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    blurb: str
    packages: tuple = ()
    services: tuple = ()
    groups: tuple = ()
    multilib: bool = False


BASE_PACKAGES = (
    "base", "linux", "linux-firmware", "networkmanager", "sudo", "nano",
    "man-db", "bash-completion", "xdg-user-dirs",
)

# Minimal Plasma: desktop, login manager, a few core apps, audio, bluetooth.
DESKTOP_PACKAGES = (
    "plasma-desktop", "sddm", "konsole", "dolphin", "kate", "ark", "firefox",
    "pipewire", "pipewire-alsa", "pipewire-pulse", "wireplumber", "plasma-pa",
    "plasma-nm", "bluez", "bluez-utils", "noto-fonts", "noto-fonts-emoji",
    "xdg-desktop-portal-kde",
)

BASE_SERVICES = ("NetworkManager", "sddm", "bluetooth", "systemd-timesyncd")

PRESETS = {
    "gaming": Preset(
        "gaming", "Gaming", "Steam, GPU drivers, Proton-ready",
        packages=("steam", "gamemode", "lib32-gamemode", "mangohud", "lib32-mangohud"),
        multilib=True,
    ),
    "coding": Preset(
        "coding", "Coding", "Git, Docker, a solid editor",
        packages=("base-devel", "git", "docker", "docker-compose", "neovim", "code"),
        services=("docker",), groups=("docker",),
    ),
    "everyday": Preset(
        "everyday", "Everyday", "Office, media and the basics",
        packages=("libreoffice-fresh", "vlc", "gwenview", "okular", "thunderbird"),
    ),
    "creating": Preset(
        "creating", "Creating", "Blender, Krita, OBS and friends",
        packages=("blender", "krita", "obs-studio", "inkscape", "gimp"),
    ),
}

# GPU vendor -> (packages, extra 32-bit packages used when multilib is on)
GPU_PACKAGES = {
    "nvidia": (("nvidia-open", "nvidia-utils", "nvidia-settings"), ("lib32-nvidia-utils",)),
    "amd": (("mesa", "vulkan-radeon"), ("lib32-mesa", "lib32-vulkan-radeon")),
    "intel": (("mesa", "vulkan-intel"), ("lib32-mesa", "lib32-vulkan-intel")),
}
# Used when the GPU is unknown (e.g. a VM) and Steam is requested: gives
# Steam's lib32-vulkan-driver dependency a deterministic provider instead of
# letting pacman pick one non-interactively.
FALLBACK_32BIT_VULKAN = ("lib32-mesa", "lib32-vulkan-radeon")
FALLBACK_VULKAN = ("mesa", "vulkan-radeon")

# Preset ids shown in the UI, in order.
PRESET_ORDER = ("gaming", "coding", "everyday", "creating")
