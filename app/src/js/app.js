var web3;
var AgentContract;
var contractInstance;
var DEFAULT_AGENT_CONTRACT_ADDRESS = "0x51554AC424A0db2B29b26b9520cD7D2Fc5F470FD";

// if (typeof web3 !== 'undefined') {
//     web3 = new Web3(web3.currentProvider);
// } else {
//     // set the provider you want from Web3.providers
// web3 = new Web3(new Web3.providers.HttpProvider("http://127.0.0.1:8545"));
// }

var CONTRACT_ABI = [
  {"constant":false,"inputs":[{"name":"_name","type":"string"},{"name":"_age","type":"uint256"},{"name":"_designation","type":"uint256"},{"name":"_hash","type":"string"}],"name":"add_agent","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"nonpayable","type":"function"},
  {"constant":false,"inputs":[{"name":"addr","type":"address"}],"name":"permit_access","outputs":[],"payable":true,"stateMutability":"payable","type":"function"},
  {"constant":false,"inputs":[{"name":"daddr","type":"address"}],"name":"revoke_access","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},
  {"constant":false,"inputs":[{"name":"paddr","type":"address"},{"name":"_diagnosis","type":"uint256"},{"name":"_hash","type":"string"}],"name":"insurance_claimm","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},
  {"constant":false,"inputs":[{"name":"paddr","type":"address"},{"name":"_hash","type":"string"}],"name":"set_hash_public","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},
  {"constant":false,"inputs":[{"name":"paddr","type":"address"},{"name":"daddr","type":"address"}],"name":"remove_patient","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},
  {"constant":true,"inputs":[{"name":"addr","type":"address"}],"name":"get_patient","outputs":[{"name":"","type":"string"},{"name":"","type":"uint256"},{"name":"","type":"uint256[]"},{"name":"","type":"address"},{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"addr","type":"address"}],"name":"get_doctor","outputs":[{"name":"","type":"string"},{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[],"name":"get_patient_list","outputs":[{"name":"","type":"address[]"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[],"name":"get_doctor_list","outputs":[{"name":"","type":"address[]"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"addr","type":"address"}],"name":"get_accessed_doctorlist_for_patient","outputs":[{"name":"","type":"address[]"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"addr","type":"address"}],"name":"get_accessed_patientlist_for_doctor","outputs":[{"name":"","type":"address[]"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"paddr","type":"address"}],"name":"get_hash","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"paddr","type":"address"},{"name":"daddr","type":"address"}],"name":"get_patient_doctor_name","outputs":[{"name":"","type":"string"},{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},
  {"constant":true,"inputs":[{"name":"paddr","type":"address"},{"name":"daddr","type":"address"}],"name":"hasAccess","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"view","type":"function"}
];

function resolveContractAddress() {
  var url = new URL(window.location.href);
  var fromQuery = url.searchParams.get("contractAddress");
  if (fromQuery) {
    window.localStorage.setItem("agentContractAddress", fromQuery);
    return fromQuery;
  }

  var fromStorage = window.localStorage.getItem("agentContractAddress");
  if (fromStorage) {
    return fromStorage;
  }

  if (window.AGENT_CONTRACT_ADDRESS) {
    return window.AGENT_CONTRACT_ADDRESS;
  }

  console.warn("Using default contract address fallback. Configure a network-specific address for production use.");
  return DEFAULT_AGENT_CONTRACT_ADDRESS;
}

function getCurrentAccount() {
  if (window.ethereum && window.ethereum.selectedAddress) {
    return window.ethereum.selectedAddress;
  }

  if (web3 && web3.eth && web3.eth.accounts && web3.eth.accounts.length > 0) {
    return web3.eth.accounts[0];
  }
  if (web3 && web3.currentProvider && web3.currentProvider.selectedAddress) {
    return web3.currentProvider.selectedAddress;
  }

  return null;
}

async function connect(){
  if (!window.ethereum) {
    throw new Error("No ethereum provider detected");
  }

  if (contractInstance) {
    return getCurrentAccount();
  }

  web3 = new Web3(window.ethereum);
  await window.ethereum.request({ method: 'eth_requestAccounts' });

  var agentContractAddress = resolveContractAddress();
  AgentContract = web3.eth.contract(CONTRACT_ABI);
  contractInstance = AgentContract.at(agentContractAddress);

  var account = getCurrentAccount();
  if (!account) {
    throw new Error("No wallet account selected in MetaMask");
  }

  web3.eth.defaultAccount = account;
  console.log("Web3 Connected:" + web3.eth.defaultAccount);

  return account;
}
    
if (window.ethereum && window.ethereum.on) {
  window.ethereum.on("accountsChanged", function(accounts) {
    if (accounts && accounts.length > 0 && web3 && web3.eth) {
      web3.eth.defaultAccount = accounts[0];
    }
  });
}

window.addEventListener('load', async function () {
  try {
    await connect();
    console.log("Externally Loaded!");
  } catch (error) {
    console.error(error);
  }
});

function getAiGatewayBase() {
  var url = new URL(window.location.href);
  var configured = url.searchParams.get("aiApiBase") || window.localStorage.getItem("aiApiBase") || window.AI_API_BASE || "";

  if (!configured) {
    configured = "http://127.0.0.1:5000";
  }

  // Default to same-origin path to avoid browser CORS issues when proxied by dev server.
  return configured.endsWith("/") ? configured.slice(0, -1) : configured;
}

function getPreliminaryDiagnosisApiUrl() {
  return getAiGatewayBase() + "/ai/preliminary-diagnosis";
}

function getSimplifiedDiagnosisApiUrl() {
  return getAiGatewayBase() + "/ai/simplify-diagnosis";
}
