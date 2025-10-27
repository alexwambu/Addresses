from flask import Flask, jsonify, send_from_directory
from web3 import Web3
from solcx import compile_source, install_solc
import json, os, threading, time, datetime

# --- Config ---
install_solc("0.8.21")
app = Flask(__name__)

RPC_URL = os.getenv("RPC_URL", "http://localhost:9636")
CHAIN_ID = int(os.getenv("CHAIN_ID", 9636))
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
GAS_WALLET = os.getenv("GAS_WALLET", "")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", 10))
DEPLOYED_FILE = "deployed_address.json"

w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)

# --- Load or create deployment file ---
if not os.path.exists(DEPLOYED_FILE):
    with open(DEPLOYED_FILE, "w") as f:
        json.dump({
            "contract_address": "",
            "network": "GBTNetwork",
            "rpc_url": RPC_URL,
            "chain_id": CHAIN_ID,
            "symbol": "GBT",
            "gas_wallet": GAS_WALLET,
            "last_updated": ""
        }, f, indent=2)

# --- Token Contract Source ---
contract_source = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;

contract GBTToken {
    string public name = "GoldBarTether";
    string public symbol = "GBT";
    uint8 public decimals = 18;
    uint256 public totalSupply;
    address public owner;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);

    constructor(uint256 initialSupply) {
        owner = msg.sender;
        totalSupply = initialSupply * (10 ** uint256(decimals));
        balanceOf[owner] = totalSupply;
        emit Transfer(address(0), owner, totalSupply);
    }

    function transfer(address _to, uint256 _value) public returns (bool success) {
        require(balanceOf[msg.sender] >= _value, "Insufficient");
        balanceOf[msg.sender] -= _value;
        balanceOf[_to] += _value;
        emit Transfer(msg.sender, _to, _value);
        return true;
    }
}
"""

compiled_sol = compile_source(contract_source, output_values=["abi", "bin"])
contract_id, contract_interface = compiled_sol.popitem()
bytecode = contract_interface["bin"]
abi = contract_interface["abi"]

# --- Helper: save deployed address ---
def save_deployed(address):
    with open(DEPLOYED_FILE, "r") as f:
        data = json.load(f)
    data["contract_address"] = address
    data["last_updated"] = datetime.datetime.utcnow().isoformat()
    with open(DEPLOYED_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- Endpoint: deploy contract ---
@app.route("/deploy", methods=["GET"])
def deploy_contract():
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account.address)
    tx = contract.constructor(1000000).build_transaction({
        "chainId": CHAIN_ID,
        "from": account.address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("1", "gwei"),
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = receipt.contractAddress
    save_deployed(contract_address)
    return jsonify({"status": "deployed", "contract_address": contract_address})

# --- Endpoint: show saved address ---
@app.route("/deployed", methods=["GET"])
def get_deployed():
    with open(DEPLOYED_FILE) as f:
        return jsonify(json.load(f))

# --- Serve HTML frontend ---
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(".", "index.html")

# --- Heartbeat ---
def heartbeat():
    while True:
        print(f"[HEARTBEAT] Alive at {datetime.datetime.utcnow().isoformat()}")
        time.sleep(HEARTBEAT_INTERVAL)

threading.Thread(target=heartbeat, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
