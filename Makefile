SHELL := /bin/zsh
.SHELLFLAGS := -eu -o pipefail -c

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(ROOT)/.venv/bin/python
PIP := $(ROOT)/.venv/bin/pip
PID_FILE := $(ROOT)/data/leaderboardle.pid
DB_FILE := $(ROOT)/data/leaderboard.sqlite3
LOG_DIR := $(ROOT)/logs
NOHUP_LOG := $(LOG_DIR)/nohup.log
BOT_PATH := /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

.PHONY: help install update deploy start stop restart status adopt logs daily-logs

help:
	@echo "Leaderboardle service commands"
	@echo "  make start       Start the bot in the background"
	@echo "  make stop        Gracefully stop the managed bot"
	@echo "  make restart     Stop, then start the bot"
	@echo "  make status      Show managed/unmanaged process status"
	@echo "  make adopt       Adopt an already-running bot into the PID file"
	@echo "  make logs        Follow stdout/nohup logs"
	@echo "  make daily-logs  Follow today's SGT application log"
	@echo "  make install     Create/update the virtual environment"
	@echo "  make update      Pull the current Git branch (fast-forward only)"
	@echo "  make deploy      Update, install dependencies, and restart"

install:
	@if [[ ! -x "$(PYTHON)" ]]; then \
		python3 -m venv "$(ROOT)/.venv"; \
	fi; \
	"$(PIP)" install -r "$(ROOT)/requirements.txt"

update:
	@git -C "$(ROOT)" pull --ff-only

deploy: update install restart

start:
	@mkdir -p "$(ROOT)/data" "$(LOG_DIR)"; \
	if [[ ! -x "$(PYTHON)" ]]; then \
		echo "Virtual environment missing. Run: make install"; \
		exit 1; \
	fi; \
	if [[ -f "$(PID_FILE)" ]]; then \
		pid=$$(<"$(PID_FILE)"); \
		if kill -0 "$$pid" 2>/dev/null; then \
			echo "Bot already running (PID $$pid)"; \
			exit 0; \
		fi; \
		echo "Removing stale PID file ($$pid)"; \
		rm -f "$(PID_FILE)"; \
	fi; \
	existing=$$(lsof -t "$(DB_FILE)" 2>/dev/null | head -n 1 || true); \
	if [[ -n "$$existing" ]]; then \
		echo "Refusing to start a duplicate: database is open by PID $$existing"; \
		echo "Run 'make adopt' to manage that process, or stop it manually first."; \
		exit 1; \
	fi; \
	cd "$(ROOT)"; \
	PATH="$(BOT_PATH):$$PATH" nohup "$(PYTHON)" -u main.py </dev/null >> "$(NOHUP_LOG)" 2>&1 & \
	pid=$$!; \
	disown "$$pid" 2>/dev/null || true; \
	echo "$$pid" > "$(PID_FILE)"; \
	sleep 2; \
	if ! kill -0 "$$pid" 2>/dev/null; then \
		echo "Bot failed to start. Last log lines:"; \
		tail -n 20 "$(NOHUP_LOG)" || true; \
		rm -f "$(PID_FILE)"; \
		exit 1; \
	fi; \
	echo "Bot started (PID $$pid)"

stop:
	@if [[ ! -f "$(PID_FILE)" ]]; then \
		echo "No managed PID file; nothing was stopped."; \
		existing=$$(lsof -t "$(DB_FILE)" 2>/dev/null | head -n 1 || true); \
		if [[ -n "$$existing" ]]; then \
			echo "An unmanaged process has the database open (PID $$existing)."; \
			echo "Use 'make adopt' first if this is the bot."; \
		fi; \
		exit 0; \
	fi; \
	pid=$$(<"$(PID_FILE)"); \
	if ! kill -0 "$$pid" 2>/dev/null; then \
		echo "Removing stale PID file ($$pid)"; \
		rm -f "$(PID_FILE)"; \
		exit 0; \
	fi; \
	kill -TERM "$$pid"; \
	for _ in {1..40}; do \
		if ! kill -0 "$$pid" 2>/dev/null; then break; fi; \
		sleep 0.25; \
	done; \
	if kill -0 "$$pid" 2>/dev/null; then \
		echo "PID $$pid did not stop after 10 seconds; not forcing it."; \
		exit 1; \
	fi; \
	rm -f "$(PID_FILE)"; \
	echo "Bot stopped (PID $$pid)"

restart: stop start

status:
	@if [[ -f "$(PID_FILE)" ]]; then \
		pid=$$(<"$(PID_FILE)"); \
		if kill -0 "$$pid" 2>/dev/null; then \
			echo "Bot is running and managed (PID $$pid)"; \
			exit 0; \
		fi; \
		echo "Bot is not running; PID file is stale ($$pid)"; \
		exit 1; \
	fi; \
	existing=$$(lsof -t "$(DB_FILE)" 2>/dev/null | head -n 1 || true); \
	if [[ -n "$$existing" ]]; then \
		echo "Bot appears to be running but unmanaged (PID $$existing)"; \
		echo "Run: make adopt"; \
	else \
		echo "Bot is not running"; \
	fi

adopt:
	@mkdir -p "$(ROOT)/data"; \
	existing=$$(lsof -t "$(DB_FILE)" 2>/dev/null | head -n 1 || true); \
	if [[ -z "$$existing" ]]; then \
		echo "No process currently has the bot database open."; \
		exit 1; \
	fi; \
	command=$$(ps -p "$$existing" -o command=); \
	if [[ "$$command" != *Python*main.py* && "$$command" != *python*main.py* ]]; then \
		echo "PID $$existing does not look like the bot: $$command"; \
		exit 1; \
	fi; \
	echo "$$existing" > "$(PID_FILE)"; \
	echo "Adopted running bot (PID $$existing)"

logs:
	@mkdir -p "$(LOG_DIR)"
	@touch "$(NOHUP_LOG)"
	@tail -n 100 -f "$(NOHUP_LOG)"

daily-logs:
	@mkdir -p "$(LOG_DIR)"; \
	today=$$(TZ=Asia/Singapore date +%F); \
	file="$(LOG_DIR)/leaderboardle-$$today.log"; \
	touch "$$file"; \
	tail -n 100 -f "$$file"
