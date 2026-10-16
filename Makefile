PY      = /usr/bin/python
ISO     = $(firstword $(wildcard out/*.iso))
OVMF_CODE = /usr/share/edk2/x64/OVMF_CODE.4m.fd
OVMF_VARS = /usr/share/edk2/x64/OVMF_VARS.4m.fd
DISK    = build/disk.qcow2
VARS    = build/OVMF_VARS.fd

.PHONY: dev test preview iso vm vm-bios vm-boot vm-reset clean

# Run the real window on this machine. Always dry-run here (see DECISIONS.md).
dev:
	$(PY) -m linusetup --windowed --dry-run

test:
	$(PY) -m unittest discover -s tests -t . -v

# Design preview in a plain browser with a mock backend.
preview:
	xdg-open "file://$(CURDIR)/linusetup/ui/index.html?mock"

# Build the ISO (asks for your sudo password; run it in a normal terminal).
iso:
	mkdir -p build out
	sudo ./iso/build.sh

build/.dirs:
	mkdir -p build && touch build/.dirs

# 30 GB virtual target disk (sparse) and a writable copy of the UEFI variable store.
$(DISK): | build/.dirs
	qemu-img create -f qcow2 $(DISK) 30G
$(VARS): | build/.dirs
	cp $(OVMF_VARS) $(VARS)

# virtio-gpu + usb-tablet: absolute pointer, so the mouse feels right in the VM.
QEMU_COMMON = qemu-system-x86_64 -enable-kvm -cpu host -m 4G -smp 2 \
	-device virtio-vga -display gtk,gl=off \
	-device qemu-xhci -device usb-tablet -device usb-kbd \
	-nic user,model=virtio-net-pci \
	-drive file=$(DISK),if=virtio,format=qcow2
QEMU_UEFI = -drive if=pflash,format=raw,readonly=on,file=$(OVMF_CODE) \
	-drive if=pflash,format=raw,file=$(VARS)

# Boot the installer ISO in UEFI mode with the empty virtual disk attached.
vm: $(DISK) $(VARS)
	@test -n "$(ISO)" || { echo "No ISO in out/. Run: make iso"; exit 1; }
	$(QEMU_COMMON) $(QEMU_UEFI) -cdrom $(ISO) -boot d

# Same, legacy BIOS (tests the GRUB path).
vm-bios: $(DISK)
	@test -n "$(ISO)" || { echo "No ISO in out/. Run: make iso"; exit 1; }
	$(QEMU_COMMON) -cdrom $(ISO) -boot d

# After installing: boot the virtual disk only, to check the installed system.
vm-boot: $(DISK) $(VARS)
	$(QEMU_COMMON) $(QEMU_UEFI)

# Fresh empty disk + firmware vars, for installing again.
vm-reset:
	rm -f $(DISK) $(VARS)

clean:
	sudo rm -rf build out
