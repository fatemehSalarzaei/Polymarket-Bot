# Wallet Setup

The bot supports one active wallet configuration. Paper trading does not require wallet setup. Real trading remains disabled by default and should only be enabled after credentials test successfully.

## Required Environment

Set a Fernet encryption key before storing wallet credentials:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the generated value to `.env`:

```bash
CREDENTIAL_ENCRYPTION_KEY=your-generated-key
```

Never commit `.env` or any real wallet/API credentials to Git.

## Configure From UI

Open `/wallet` in the frontend and enter:

- Private Key
- Funder Address, if using a proxy/deposit wallet
- Signature Type
- Chain ID, usually `137` for Polygon
- Create or derive API credentials

The private key is sent only to the backend, stored encrypted, and never returned to the frontend. API secret and passphrase are never displayed.

## Signature Types

- `0`: EOA
- `1`: POLY_PROXY
- `2`: GNOSIS_SAFE
- `3`: POLY_1271 / Deposit Wallet

## Why The Private Key Is Required

Polymarket CLOB API credentials are created or derived using L1 wallet authentication. Creating real orders also requires local signing with the wallet private key. Use a dedicated trading wallet with limited funds.

## Paper Trading

Paper trading uses simulated local orders and does not require wallet credentials, API credentials, or real funds.
