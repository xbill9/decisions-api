GEMMA_RIG ?= $(HOME)/gemma4-dev/local-llamacpp-cpu-2b-q4_0

.PHONY: help install gemma smoke bench scale agent web lint test

help:
	@echo "make install   pip deps into the system python3"
	@echo "make gemma     serve Gemma 4 E2B on CPU at 127.0.0.1:8080 (foreground)"
	@echo "make smoke     one ticket through every backend"
	@echo "make bench     48 labeled tickets x {decisions, gemma, flashlite}"
	@echo "make scale     latency for 1..100 questions per request"
	@echo "make agent     ADK triage agent in the terminal"
	@echo "make web       ADK web UI on localhost:8000"
	@echo "make test      offline tests (no network, no key, no Gemma)"

install:
	pip install -r requirements.txt

gemma:
	$(MAKE) -C $(GEMMA_RIG) serve

smoke:
	python3 -c "from decide import BACKENDS, pick; from tickets import QUESTIONS, TICKETS; \
	t = TICKETS[0][0]; print(t); \
	[print(n, f'{(r := f(t, QUESTIONS))[\"latency_s\"]*1000:.0f} ms', {k: pick(a) for k, a in r['answers'].items()}) for n, f in BACKENDS.items()]"

bench:
	python3 bench.py

scale:
	python3 scale.py --backends decisions,gemma,flashlite --reps 3

agent:
	adk run triage_agent

web:
	adk web .

lint:
	ruff check .

test:
	env -u GEMINI_API_KEY -u GOOGLE_API_KEY python3 -m pytest -q
