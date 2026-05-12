BIN := $(HOME)/.local/bin/ccp

install:
	mkdir -p $(HOME)/.local/bin
	ln -sf $(abspath ccp.py) $(BIN)
	chmod +x ccp.py
	@echo "Installed: $(BIN)"
	@echo "Run 'ccp --help' to get started."

uninstall:
	rm -f $(BIN)
	@echo "Uninstalled: $(BIN)"

.PHONY: install uninstall
