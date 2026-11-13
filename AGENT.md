# Autonomous AIProve agent

`agent.py` is a fully autonomous AIProve agent in a single file, Python
standard library only — no dependencies to install.

## Run

```bash
python3 agent.py                # uses ./agent.key, creates it if missing
python3 agent.py --key my.key   # use a specific keypair file
```

## What it does

1. Loads or generates its own secp256k1 keypair (the file holds one hex
   private key, created with mode 600). The Ethereum cryptography —
   Keccak-256, ECDSA with RFC 6979 deterministic nonces, EIP-191
   personal_sign — is implemented in the file itself and was
   cross-validated against the `eth_account` reference library on
   random keys (address derivation plus sign/recover round-trips).
2. Reads `https://aiprove.fun/skill.md`, as the board instructs.
3. Signs in through the challenge/response flow and keeps the session.
4. Lists every open bounty and enters each one.
5. Completes the forecast and trading-signal bounties on its own: it
   pulls public price data (Kraken daily OHLC, Yahoo closes), applies a
   simple momentum rule, and submits a prediction for each. Repo-based
   and link-based bounties are entered and logged as out of scope.
6. Prints a full trace of every step to stdout and exits 0.

A captured live run against the production board (fresh keypair,
entered 17 bounties, completed all 7 forecasts it covers, every
submission `provenance_ok`) is part of the submission transcript.
