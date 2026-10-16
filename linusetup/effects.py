"""How much animation the UI can afford on this machine.

  minimal   integrated GPUs, weak dedicated GPUs, VMs, low RAM or few cores
  balanced  solid mid-range dedicated GPUs
  full      strong dedicated GPUs

Classified from the GPU names lspci reports (pci.ids). The UI can still step
down if it measures a low frame rate, and the user can override it.
"""
import re

TIERS = ("minimal", "balanced", "full")
INTEGRATED, WEAK, MID, STRONG = 0, 1, 2, 3

# AMD APU (integrated) codenames as they appear in pci.ids
AMD_APUS = ("renoir", "cezanne", "lucienne", "barcelo", "rembrandt", "phoenix", "hawk point", "raphael",
            "granite ridge", "strix", "krackan", "mendocino", "van gogh", "picasso", "raven", "dali",
            "pollock", "stoney", "carrizo", "kaveri", "kabini", "mullins", "beema", "radeon vega series",
            "radeon vega mobile", "vega 8", "vega 7", "vega 6", "vega 3")


def classify_gpu(vendor, name):
    """(score, kind) for one GPU. vendor: nvidia|amd|intel|other; name: lspci text."""
    n = name.lower()
    if vendor == "nvidia":
        if "titan" in n:
            return STRONG, "high-end"
        m = re.search(r"rtx a(\d{4})", n)
        if m:
            return (STRONG if int(m.group(1)) >= 4000 else MID), "workstation"
        m = re.search(r"rtx (\d{4})", n)
        if m:
            rank = int(m.group(1)) // 10 % 10
            return (STRONG if rank >= 7 else MID), "dedicated"
        m = re.search(r"gtx (\d{3,4})", n)
        if m:
            d = int(m.group(1))
            return (MID if d >= 1000 and d // 10 % 10 >= 6 else WEAK), "dedicated"
        if re.search(r"\b(gt|mx|nvs) ?\d", n) or "quadro p4" in n or "quadro k" in n:
            return WEAK, "entry-level"
        if "quadro" in n:
            return MID, "workstation"
        return MID, "dedicated"
    if vendor == "amd":
        if any(a in n for a in AMD_APUS) or re.search(r"radeon \d{3}m\b", n):
            return INTEGRATED, "integrated"
        if "vega 56" in n or "vega 64" in n or "radeon vii" in n:
            return MID, "dedicated"
        m = re.search(r"rx ([\d/ a-z]+)", n)
        if m:
            nums = [int(x) for x in re.findall(r"\d{3,4}", m.group(1))]
            if nums:
                d = max(nums)
                if d < 1000:                                   # RX 4xx / 5xx
                    return WEAK, "dedicated"
                series = d // 1000
                rank = d // 10 % 10 if series == 9 else d // 100 % 10
                if series == 5:
                    return (MID if rank >= 6 else WEAK), "dedicated"
                return (STRONG if rank >= 7 else MID if rank == 6 else WEAK), "dedicated"
        if "radeon pro" in n:
            return MID, "workstation"
        return WEAK, "unknown AMD"
    if vendor == "intel":
        m = re.search(r"arc ([ab])(\d{3})", n)
        if m:
            return (WEAK if m.group(1) == "a" and int(m.group(2)) < 500 else MID), "dedicated"
        return INTEGRATED, "integrated"
    return INTEGRATED, "basic display"


def choose(hw, override=None):
    """-> dict(tier, reason, gpu, auto). override: one of TIERS, or None/'auto'."""
    best, best_gpu, kind = INTEGRATED, None, "none"
    for vendor, name in hw.gpus:
        score, k = classify_gpu(vendor, name)
        if best_gpu is None or score > best:
            best, best_gpu, kind = score, name, k
    tier = {INTEGRATED: "minimal", WEAK: "minimal", MID: "balanced", STRONG: "full"}[best]
    gpu = best_gpu or "no GPU detected"
    reason = f"{gpu} ({kind})"
    if hw.virt:
        tier, reason = "minimal", f"virtual machine ({hw.virt}): graphics are rendered by the CPU"
    elif not getattr(hw, "render_node", True):
        tier, reason = "minimal", "no GPU acceleration available"
    elif hw.ram_gb and hw.ram_gb < 4:
        tier, reason = "minimal", f"only {hw.ram_gb} GB of memory"
    elif getattr(hw, "cpu_cores", 0) and hw.cpu_cores <= 2:
        tier, reason = "minimal", f"only {hw.cpu_cores} CPU threads"
    elif tier == "full" and hw.ram_gb and hw.ram_gb < 8:
        tier, reason = "balanced", f"{reason}, but {hw.ram_gb} GB of memory"
    if override in TIERS:
        return dict(tier=override, reason=f"chosen manually (detected: {tier}, {reason})", gpu=gpu, auto=False, detected=tier)
    return dict(tier=tier, reason=reason, gpu=gpu, auto=True, detected=tier)


def needs_software_rendering(hw):
    """WebKit's GPU compositing breaks or crawls without real acceleration (VMs)."""
    return bool(hw.virt) or not getattr(hw, "render_node", True)
