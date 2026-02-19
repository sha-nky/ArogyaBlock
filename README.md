# ArogyaBlock

ArogyaBlock is a blockchain-enabled electronic medical records (EMR) demo application built with:

- **Solidity + Truffle** for smart contracts
- **Web3.js + static HTML/JS UI** for dApp interaction
- **IPFS** for off-chain record content storage
- An optional **ML prediction API** used during doctor diagnosis workflows

The project models two actor roles:

- **Patient**: registers, stores/retrieves records, grants/revokes doctor access
- **Doctor**: views permitted patient records, appends diagnosis, submits insurance claim flow

---

## Repository Structure

```text
.
├── README.md
└── app/
    ├── contracts/            # Solidity contracts
    │   ├── Agent.sol
    │   └── Migrations.sol
    ├── migrations/           # Truffle deployment scripts
    ├── src/                  # Frontend HTML/CSS/JS
    │   ├── index.html        # Login page
    │   ├── register.html     # Role registration
    │   ├── patient.html      # Patient dashboard
    │   ├── doctor.html       # Doctor dashboard
    │   └── js/app.js         # Shared dApp connection logic + ABI
    ├── test/                 # Truffle tests
    ├── truffle-config.js
    ├── bs-config.json        # lite-server + proxy config
    └── package.json
```

---

## Core Functional Flow

1. **Connect wallet** (MetaMask) from frontend pages.
2. **Register** as patient or doctor via `add_agent`.
3. **Patient grants access** to a doctor by paying an exact `2 ether` access fee into contract pool.
4. **Doctor reads patient record** hash and content from IPFS.
5. **Doctor submits diagnosis** (optionally enriched with ML prediction API response).
6. **Insurance claim flow** updates record hash, pays out from contract pool, and removes doctor access.
7. **Patient can revoke access** and receive refund if claim not consumed.

---

## Smart Contract Summary (`Agent.sol`)

### State

- `ACCESS_FEE = 2 ether`
- `creditPool` tracks pooled access fees
- Patient and doctor registries with role-specific access lists
- Patient record field stores IPFS hash

### Main functions

- `add_agent(name, age, designation, hash)`
  - designation `0` => patient, `1` => doctor
- `permit_access(doctor)` *(payable, exact fee required)*
- `revoke_access(doctor)`
- `insurance_claimm(patient, diagnosis, hash)`
- `set_hash_public(patient, hash)`
- `get_patient`, `get_doctor`, `get_hash`, list getters, and `hasAccess`

### Events

- `AgentAdded`
- `AccessPermitted`
- `AccessRevoked`
- `RecordHashUpdated`
- `InsuranceClaimProcessed`

---

## Prerequisites

Install these locally before running:

- **Node.js** (LTS recommended)
- **npm**
- **Ganache** (or another local Ethereum RPC network)
- **MetaMask** browser extension
- **IPFS daemon/API** reachable at `localhost:5001`
- **IPFS gateway** reachable at `localhost:8080`
- *(Optional but used by doctor workflow)* ML backend serving `POST /predict` (default expected at `127.0.0.1:5000`)

> Note: This project currently uses legacy Web3/Truffle-era patterns and Solidity 0.5.x contract syntax.

---

## Setup and Run

From repository root:

```bash
cd app
npm install
```

### 1) Start blockchain network

Run Ganache on:

- Host: `127.0.0.1`
- Port: `7545`

(These values match `truffle-config.js`.)

### 2) Compile and deploy contracts

```bash
npx truffle compile
npx truffle migrate --reset
```

Copy deployed `Agent` contract address from migration output.

### 3) Start IPFS services

Ensure:

- API: `localhost:5001`
- Gateway: `localhost:8080`

### 4) (Optional) Start ML prediction backend

The frontend uses either:

- relative `/predict` (proxied by lite-server to `127.0.0.1:5000`), or
- override using query string `?mlApiBase=http://host:port`

### 5) Start frontend

```bash
npm run dev
```

Open the URL printed by lite-server.

### 6) Connect MetaMask to local chain

- Import/test accounts from Ganache
- Ensure active network matches the chain used for deployment
- Use one account per role for clear testing

### 7) Configure contract address in UI

The app resolves contract address in this order:

1. `contractAddress` query string
2. `localStorage.agentContractAddress`
3. `window.AGENT_CONTRACT_ADDRESS`
4. hardcoded fallback in `src/js/app.js`

Recommended launch URL pattern:

```text
http://localhost:3000/index.html?contractAddress=0xYourDeployedAddress
```

---

## Testing

Run contract tests:

```bash
cd app
npm test
```

This executes:

- registration role checks
- access fee / pool behavior checks
- unauthorized removal revert check
- revoke and refund behavior check

---

## Configuration Notes

- `truffle-config.js` points development network to `127.0.0.1:7545`.
- `bs-config.json` serves from `src/` and proxies API calls to `127.0.0.1:5000`.
- Frontend IPFS endpoints are currently hardcoded to localhost.

For multi-environment usage, centralize these values via build/runtime config.

---

## Troubleshooting

### MetaMask not connecting

- Verify extension is installed and unlocked
- Confirm site permission to access accounts
- Ensure chain/network matches Ganache chain

### Transactions fail/revert

- Confirm role registration before role-specific actions
- `permit_access` must send **exactly** `2 ether`
- Ensure patient-doctor link exists for doctor claim operations

### Records not loading

- Check IPFS daemon and gateway availability
- Validate saved hash exists in IPFS

### Prediction API errors

- Start backend at `127.0.0.1:5000`, or
- pass `?mlApiBase=http://<host>:<port>` in URL

### Truffle command download issues

- Install `truffle` as a local dev dependency or globally in restricted environments
- Avoid relying on ad-hoc `npx` downloads where registry access is blocked

---

## Security and Privacy Considerations

This repository is a prototype and should be hardened before production use:

- Enforce stricter on-chain access controls for sensitive reads
- Use secure key management and contract upgrade strategy
- Replace localhost hardcoding with environment-based config
- Add CI, linting, audit tooling, and broader contract test coverage
- Evaluate data minimization and compliance requirements for medical data

---

## License

No explicit license file is present in this repository at the time of writing.
