PY        = /usr/bin/python
ISO       = $(lastword $(sort $(wildcard out/*.iso)))
OVMF_CODE = /usr/share/edk2/x64/OVMF_CODE.4m.fd
OVMF_VARS = /usr/share/edk2/x64/OVMF_VARS.4m.fd
DISK      = build/disk.qcow2
VARS      = build/OVMF_VARS.fd
CONFIG   ?= tests/e2e/ext4-uefi.json
PROXY_PORT = 8081
# A caching package mirror for test VMs: each package is downloaded once, then
# served from build/vmcache (seeded with the ISO build's packages).
PROXY = $(PY) tools/pkgproxy.py --port $(PROXY_PORT) --cache build/vmcache --seed build/pkgcache \
	>> build/vmcache.log 2>&1 & echo $$! > build/.proxy.pid
PROXY_STOP = kill $$(cat build/.proxy.pid) 2>/dev/null; rm -f build/.proxy.pid; \
	tail -1 build/vmcache.log
QEMU_PROXY = -fw_cfg name=opt/linusetup/mirror,string=http://10.0.2.2:$(PROXY_PORT)

.PHONY: help dev demo preview test filesdb selftest screens iso vm vm-bios vm-boot vm-reset e2e e2e-all clean

help:
	@echo "make dev        the real window on this machine (always a dry run here)"
	@echo "make demo       the window with pretend hardware (Windows disk, BitLocker disk...)"
	@echo "make preview    the UI in your browser at http://127.0.0.1:8765 (pretend hardware)"
	@echo "make test       all unit, image and package tests"
	@echo "make selftest   click through the whole UI headlessly (Firefox + WebKitGTK, 3 sizes)"
	@echo "make screens    screenshots of every screen into build/screens/"
	@echo "make iso        build the live ISO (sudo); RELEASE=1 for the small, slow xz build"
	@echo "make vm         boot the ISO in QEMU (UEFI) with an empty 30 GB disk"
	@echo "make e2e        unattended install + boot + login check of CONFIG in QEMU"
	@echo "make e2e-all    every config in tests/e2e/"

dev:
	$(PY) -m linusetup --windowed --dry-run

demo:
	$(PY) -m linusetup --windowed --fixtures

preview:
	$(PY) -m linusetup serve

test:
	$(PY) -m unittest discover -s tests -t .

filesdb:
	tools/fetch_filesdb.sh

selftest:
	FX=full tools/selftest.sh firefox 1280x800 && FX=balanced tools/selftest.sh firefox 1024x768 && \
	FX=minimal tools/selftest.sh firefox 800x600 && tools/selftest.sh webkit 1280x800 && \
	FX=full tools/selftest.sh webkit 1280x800

screens:
	tools/screens.sh 1280x800

# Build the ISO (asks for your sudo password; run it in a normal terminal).
# build/ and out/ are created as you first, so later targets don't need root.
iso:
	mkdir -p build out
	sudo nice -n 15 ionice -c 3 ./iso/build.sh $(if $(RELEASE),--release)

build/.dirs:
	mkdir -p build && touch build/.dirs
$(DISK): | build/.dirs
	qemu-img create -f qcow2 $(DISK) 30G
$(VARS): | build/.dirs
	cp $(OVMF_VARS) $(VARS)

# virtio-gpu + usb-tablet: absolute pointer, so the mouse feels right in the VM.
QEMU_COMMON = qemu-system-x86_64 -enable-kvm -cpu host -m 4G -smp 4 \
	-device virtio-vga -display gtk,gl=off \
	-device qemu-xhci -device usb-tablet -device usb-kbd \
	-nic user,model=virtio-net-pci \
	-drive file=$(DISK),if=virtio,format=qcow2,cache=unsafe,discard=unmap
QEMU_UEFI = -drive if=pflash,format=raw,readonly=on,file=$(OVMF_CODE) \
	-drive if=pflash,format=raw,file=$(VARS)

vm: $(DISK) $(VARS)
	@test -n "$(ISO)" || { echo "No ISO in out/. Run: make iso"; exit 1; }
	@$(PROXY)
	-$(QEMU_COMMON) $(QEMU_UEFI) $(QEMU_PROXY) -cdrom $(ISO) -boot once=d
	@$(PROXY_STOP)

vm-bios: $(DISK)
	@test -n "$(ISO)" || { echo "No ISO in out/. Run: make iso"; exit 1; }
	@$(PROXY)
	-$(QEMU_COMMON) $(QEMU_PROXY) -cdrom $(ISO) -boot once=d
	@$(PROXY_STOP)

vm-boot: $(DISK) $(VARS)
	$(QEMU_COMMON) $(QEMU_UEFI)

vm-reset:
	rm -f $(DISK) $(VARS)

e2e:
	$(PY) tools/e2e.py $(CONFIG)

e2e-all:
	@fail=0; for f in tests/e2e/*.json; do $(PY) tools/e2e.py --quiet $$f || fail=1; done; exit $$fail

clean:
	sudo rm -rf build out
