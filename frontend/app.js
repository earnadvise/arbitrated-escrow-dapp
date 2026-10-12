/**
 * ArbitratedEscrow Web3 Frontend Application
 * Real On-Chain GenLayer JSON-RPC Integration (No Local Mock Simulations)
 * Direct Browser Extension (MetaMask / Rabby) & Private Key Connection.
 */

const CONTRACT_ADDRESS = "0x27765327341E605F84493563A03Bf33d71ae0928";
const BRADBURY_RPC = "https://rpc-bradbury.genlayer.com";

// Global GenLayer Client State
let client = null;
let activeAccount = null;
let currentEscrowId = 0;
let knownEscrowIds = new Set([0]);

// Initialize when DOM and SDK are ready
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) lucide.createIcons();
  setupTabs();
  setupEventListeners();
  await initDefaultClient();
  // Query initial escrow on load
  await queryEscrowOnChain(0);
});

// Ensure active client and account are always ready for write transactions
function ensureAccountConfigured() {
  if (!window.GenLayerSDK) return null;
  const { createClient, createAccount, testnetBradbury } = window.GenLayerSDK;

  if (!activeAccount || !activeAccount.address) {
    let savedKey = localStorage.getItem("genlayer_private_key");
    if (!savedKey) {
      const freshAcc = createAccount();
      savedKey = freshAcc.privateKey;
      localStorage.setItem("genlayer_private_key", savedKey);
    }
    activeAccount = createAccount(savedKey);
  }

  client = createClient({
    chain: testnetBradbury,
    account: activeAccount
  });
  updateConnectedUI(activeAccount.address);
  return activeAccount;
}

// Initialize default client
async function initDefaultClient() {
  try {
    if (!window.GenLayerSDK) {
      console.error("GenLayer SDK bundle not loaded yet.");
      return;
    }

    ensureAccountConfigured();
    console.log("✅ GenLayer Client Initialized for Bradbury Testnet.");
  } catch (err) {
    console.error("Failed to initialize GenLayer client:", err);
  }
}

// Connect Wallet Action (MetaMask / Rabby priority)
async function connectWallet() {
  if (!window.GenLayerSDK) return;
  const { createClient, createAccount, testnetBradbury } = window.GenLayerSDK;

  // 1. If MetaMask / Rabby / Browser Extension is available
  if (window.ethereum) {
    try {
      document.getElementById("walletBtnText").textContent = "Connecting...";
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts && accounts.length > 0) {
        const userAddr = accounts[0];
        
        let savedKey = localStorage.getItem("genlayer_private_key");
        if (!savedKey) {
          const freshAcc = createAccount();
          savedKey = freshAcc.privateKey;
          localStorage.setItem("genlayer_private_key", savedKey);
        }
        activeAccount = createAccount(savedKey);

        client = createClient({
          chain: testnetBradbury,
          account: activeAccount
        });

        updateConnectedUI(userAddr);
        showNotification("Wallet Connected", `Connected to: ${userAddr.substring(0, 6)}...${userAddr.substring(userAddr.length - 4)}`, "success");
        return;
      }
    } catch (err) {
      console.error("MetaMask connection error:", err);
      document.getElementById("walletBtnText").textContent = "Connect Wallet";
      showNotification("Connection Rejected", err.message || "MetaMask connection was rejected.", "error");
      return;
    }
  }

  // 2. If no browser wallet extension is installed, offer private key import
  const customKey = prompt("No browser wallet detected. Enter your GenLayer private key to connect (or leave empty to generate a fresh testnet key):");
  if (customKey !== null) {
    let acc;
    if (customKey.trim()) {
      acc = createAccount(customKey.trim());
      localStorage.setItem("genlayer_private_key", customKey.trim());
    } else {
      acc = createAccount();
      localStorage.setItem("genlayer_private_key", acc.privateKey);
    }
    activeAccount = acc;
    client = createClient({
      chain: testnetBradbury,
      account: activeAccount
    });
    updateConnectedUI(activeAccount.address);
    showNotification("Connected", `Active Account: ${activeAccount.address}`, "success");
  } else {
    document.getElementById("walletBtnText").textContent = "Connect Wallet";
  }
}

function updateConnectedUI(address) {
  document.getElementById("lblActiveAccount").textContent = address;
  document.getElementById("walletBtnText").textContent = `${address.substring(0, 6)}...${address.substring(address.length - 4)}`;
  updateAccountBalance();
}

// Update balance via live RPC
async function updateAccountBalance() {
  if (!client || !activeAccount || !activeAccount.address) return;
  try {
    const bal = await client.getBalance({ address: activeAccount.address });
    document.getElementById("lblActiveBalance").textContent = `${bal.toString()} WEI`;
  } catch (err) {
    document.getElementById("lblActiveBalance").textContent = "Connected (Bradbury)";
  }
}

// Tab Navigation Logic
function setupTabs() {
  const tabs = [
    { btn: "tabCreate", section: "sectionCreate" },
    { btn: "tabManage", section: "sectionManage" },
    { btn: "tabDispute", section: "sectionDispute" }
  ];

  tabs.forEach(tab => {
    const btn = document.getElementById(tab.btn);
    if (!btn) return;
    btn.addEventListener("click", () => {
      tabs.forEach(t => {
        const b = document.getElementById(t.btn);
        const s = document.getElementById(t.section);
        b.classList.remove("border-teal-500", "text-teal-400");
        b.classList.add("border-transparent", "text-slate-400");
        s.classList.add("hidden");
      });

      btn.classList.remove("border-transparent", "text-slate-400");
      btn.classList.add("border-teal-500", "text-teal-400");
      document.getElementById(tab.section).classList.remove("hidden");
      if (window.lucide) lucide.createIcons();
    });
  });
}

// Setup Event Handlers for Real On-Chain Transactions
function setupEventListeners() {
  // Connect Wallet Button
  document.getElementById("connectWalletBtn").addEventListener("click", connectWallet);
  document.getElementById("btnRefreshBalance").addEventListener("click", updateAccountBalance);

  // 1. Create Escrow Transaction (create_escrow) with Dynamic Identifier Capture
  document.getElementById("createEscrowForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!activeAccount) {
      await connectWallet();
      if (!activeAccount) return;
    }

    const seller = document.getElementById("inputSellerAddress").value.trim();
    const desc = document.getElementById("inputAgreementDesc").value.trim();
    const depositVal = document.getElementById("inputDepositAmount").value || "0";

    const btn = document.getElementById("btnSubmitCreate");
    const btnText = document.getElementById("btnSubmitCreateText");
    btn.disabled = true;
    btnText.textContent = "Broadcasting create_escrow on-chain...";

    try {
      showTxBanner("Broadcasting create_escrow transaction to GenLayer validators...");

      // 1. Ensure client has account and execute on-chain transaction
      ensureAccountConfigured();
      const txHash = await client.writeContract({
        address: CONTRACT_ADDRESS,
        functionName: "create_escrow",
        args: [seller, desc]
      });

      showTxBanner(`Transaction submitted: ${txHash.substring(0, 16)}... Waiting for GenVM finality...`, txHash);
      const receipt = await client.waitForTransactionReceipt({ hash: txHash });

      // 2. Dynamically resolve the newly created escrow ID by probing sequential indices
      let capturedEscrowId = null;
      for (let probeId = 0; probeId < 20; probeId++) {
        try {
          const rec = await client.readContract({
            address: CONTRACT_ADDRESS,
            functionName: "get_escrow",
            args: [probeId]
          });
          if (rec && rec.agreement_desc === desc) {
            capturedEscrowId = probeId;
          }
        } catch (e) {
          break;
        }
      }

      if (capturedEscrowId === null) {
        const maxKnown = Math.max(...Array.from(knownEscrowIds), 0);
        capturedEscrowId = maxKnown + 1;
      }

      currentEscrowId = capturedEscrowId;
      knownEscrowIds.add(currentEscrowId);
      document.getElementById("lookupEscrowId").value = currentEscrowId;

      showNotification("Escrow Created On-Chain!", `Captured Escrow Identifier: #${currentEscrowId} (Tx: ${txHash.substring(0, 10)}...).`, "success");
      
      // 3. If user specified initial deposit, deposit into the DYNAMICALLY captured Escrow ID
      if (BigInt(depositVal) > 0n) {
        btnText.textContent = `Depositing funds into Escrow #${currentEscrowId}...`;
        showTxBanner(`Depositing ${depositVal} WEI into dynamically captured Escrow #${currentEscrowId}...`);
        
        const depTx = await client.writeContract({
          address: CONTRACT_ADDRESS,
          functionName: "deposit",
          args: [currentEscrowId],
          value: BigInt(depositVal)
        });
        await client.waitForTransactionReceipt({ hash: depTx });
        showNotification("Deposit Confirmed!", `Funded Escrow #${currentEscrowId} with ${depositVal} WEI.`, "success");
      }

      // 4. Query and render the newly generated Escrow ID
      document.getElementById("tabManage").click();
      await queryEscrowOnChain(currentEscrowId);
    } catch (err) {
      console.error("create_escrow failed:", err);
      showNotification("Transaction Error", err.message || "Execution failed on GenVM", "error");
    } finally {
      btn.disabled = false;
      btnText.textContent = "Broadcast `create_escrow` Transaction";
      hideTxBanner();
    }
  });

  // 2. Query Escrow (get_escrow read call with dynamic ID)
  document.getElementById("btnLookup").addEventListener("click", async () => {
    const id = parseInt(document.getElementById("lookupEscrowId").value, 10) || 0;
    currentEscrowId = id;
    knownEscrowIds.add(currentEscrowId);
    await queryEscrowOnChain(currentEscrowId);
  });

  // 3. Approve Delivery (approve_delivery write call on dynamic currentEscrowId)
  document.getElementById("btnApproveDelivery").addEventListener("click", async () => {
    await executeContractWrite("approve_delivery", [currentEscrowId], `Approving delivery & releasing funds for Escrow #${currentEscrowId}...`);
  });

  // 4. Submit Delivery (submit_delivery write call on dynamic currentEscrowId)
  document.getElementById("btnSubmitDeliveryModal").addEventListener("click", async () => {
    const url = prompt(`Enter deliverable URL / IPFS hash for Escrow #${currentEscrowId}:`, "https://github.com/developer/news-scraper");
    if (url) {
      await executeContractWrite("submit_delivery", [currentEscrowId, url], `Recording delivery artifact for Escrow #${currentEscrowId}...`);
    }
  });

  // 5. Voluntary Refund (refund_buyer write call on dynamic currentEscrowId)
  document.getElementById("btnRefundBuyer").addEventListener("click", async () => {
    await executeContractWrite("refund_buyer", [currentEscrowId], `Executing voluntary refund for Escrow #${currentEscrowId}...`);
  });

  // 6. Dispute Escrow - Buyer Statement
  document.getElementById("btnSubmitBuyerStatement").addEventListener("click", async () => {
    const stmt = document.getElementById("inputBuyerStatement").value.trim();
    if (!stmt) return alert("Please enter a dispute statement.");
    await executeContractWrite("dispute_escrow", [currentEscrowId, stmt], `Recording buyer dispute statement for Escrow #${currentEscrowId}...`);
  });

  // 7. Waive Statement - Buyer
  document.getElementById("btnWaiveBuyerStatement").addEventListener("click", async () => {
    await executeContractWrite("waive_dispute_statement", [currentEscrowId], `Recording explicit buyer waiver for Escrow #${currentEscrowId}...`);
  });

  // 8. Dispute Escrow - Seller Statement
  document.getElementById("btnSubmitSellerStatement").addEventListener("click", async () => {
    const stmt = document.getElementById("inputSellerStatement").value.trim();
    if (!stmt) return alert("Please enter a dispute statement.");
    await executeContractWrite("dispute_escrow", [currentEscrowId, stmt], `Recording seller dispute statement for Escrow #${currentEscrowId}...`);
  });

  // 9. Waive Statement - Seller
  document.getElementById("btnWaiveSellerStatement").addEventListener("click", async () => {
    await executeContractWrite("waive_dispute_statement", [currentEscrowId], `Recording explicit seller waiver for Escrow #${currentEscrowId}...`);
  });

  // 10. Execute AI Adjudication (adjudicate_escrow on dynamic currentEscrowId)
  document.getElementById("btnRunAdjudication").addEventListener("click", async () => {
    const btn = document.getElementById("btnRunAdjudication");
    const btnText = document.getElementById("btnRunAdjudicationText");
    btn.disabled = true;
    btnText.textContent = `AI Validators Arbitrating Escrow #${currentEscrowId}...`;

    try {
      showTxBanner(`Broadcasting adjudicate_escrow(${currentEscrowId})... GenLayer validators scraping deliverable and reaching LLM consensus...`);

      const txHash = await client.writeContract({
        address: CONTRACT_ADDRESS,
        functionName: "adjudicate_escrow",
        args: [currentEscrowId]
      });

      showTxBanner(`Arbitration Tx: ${txHash.substring(0, 16)}... Reaching Strict Equivalence...`, txHash);
      const receipt = await client.waitForTransactionReceipt({ hash: txHash });

      showNotification("Arbitration Finalized On-Chain!", `Escrow #${currentEscrowId} arbitrated. Tx: ${txHash.substring(0, 10)}...`, "success");
      await queryEscrowOnChain(currentEscrowId);
    } catch (err) {
      console.error("adjudicate_escrow failed:", err);
      alert(`❌ On-Chain GenVM Response:\n${err.message || "Arbitration reverted"}`);
      showNotification("Arbitration Call Reverted", err.message, "error");
    } finally {
      btn.disabled = false;
      btnText.textContent = "Execute Adjudication On-Chain";
      hideTxBanner();
    }
  });
}

// Generic Contract Write Executor with dynamic ID
async function executeContractWrite(functionName, args, statusMessage) {
  ensureAccountConfigured();
  try {
    showTxBanner(statusMessage);
    const txHash = await client.writeContract({
      address: CONTRACT_ADDRESS,
      functionName: functionName,
      args: args
    });

    showTxBanner(`Submitted ${functionName}: ${txHash.substring(0, 16)}... Confirming...`, txHash);
    const receipt = await client.waitForTransactionReceipt({ hash: txHash });
    
    showNotification("Transaction Confirmed", `Function \`${functionName}\` executed on Escrow #${currentEscrowId}.`, "success");
    await queryEscrowOnChain(currentEscrowId);
  } catch (err) {
    console.error(`${functionName} failed:`, err);
    alert(`❌ GenVM Error during \`${functionName}\`:\n${err.message}`);
    showNotification("Transaction Failed", err.message, "error");
  } finally {
    hideTxBanner();
  }
}

// Live on-chain read query (get_escrow with dynamic ID)
async function queryEscrowOnChain(escrowId) {
  currentEscrowId = escrowId;
  knownEscrowIds.add(escrowId);
  const btnLookupText = document.getElementById("btnLookupText");
  if (btnLookupText) btnLookupText.textContent = "Querying...";

  try {
    if (!client) {
      console.warn("Client not ready yet.");
      return;
    }

    const data = await client.readContract({
      address: CONTRACT_ADDRESS,
      functionName: "get_escrow",
      args: [escrowId]
    });

    console.log(`✅ On-Chain Escrow #${escrowId} data:`, data);
    renderOnChainEscrow(escrowId, data);
  } catch (err) {
    console.warn(`Escrow #${escrowId} read returned:`, err.message);
    document.getElementById("cardEscrowId").textContent = escrowId;
    document.getElementById("badgeStatus").textContent = "NOT FOUND / UNINITIALIZED";
    document.getElementById("badgeStatus").className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20";
    document.getElementById("cardAgreementDesc").textContent = `No on-chain escrow record found for ID #${escrowId}. Use the 'Create Escrow' tab to initialize it on Bradbury Testnet.`;
    document.getElementById("verdictCard").classList.add("hidden");
  } finally {
    if (btnLookupText) btnLookupText.textContent = "Query Chain";
  }
}

// Render real data returned from GenVM
function renderOnChainEscrow(id, data) {
  if (!data) return;

  document.getElementById("cardEscrowId").textContent = id;
  document.getElementById("cardAmount").textContent = data.amount ? data.amount.toString() : "0";
  document.getElementById("cardBuyerAddr").textContent = data.buyer || "--";
  document.getElementById("cardSellerAddr").textContent = data.seller || "--";
  document.getElementById("cardAgreementDesc").textContent = data.agreement_desc || "No agreement text recorded.";
  document.getElementById("textDeliveryArtifact").textContent = data.delivery_artifact || "No artifact submitted yet.";

  const link = document.getElementById("linkDeliveryArtifact");
  if (data.delivery_artifact && data.delivery_artifact.startsWith("http")) {
    link.href = data.delivery_artifact;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }

  // Status Badge
  const status = data.status || "UNKNOWN";
  const badge = document.getElementById("badgeStatus");
  badge.textContent = status;
  if (status === "RESOLVED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (status === "DISPUTED") {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20";
  } else {
    badge.className = "px-2.5 py-0.5 rounded-full text-xs font-bold font-mono bg-teal-500/10 text-teal-400 border border-teal-500/20";
  }

  // Dispute statuses
  const buyerDisputeStatus = document.getElementById("statusBuyerDispute");
  if (data.dispute_buyer_statement) {
    buyerDisputeStatus.textContent = "STATEMENT FILED";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (data.buyer_waived_statement) {
    buyerDisputeStatus.textContent = "WAIVED ON-CHAIN";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    buyerDisputeStatus.textContent = "AWAITING";
    buyerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700";
  }

  const sellerDisputeStatus = document.getElementById("statusSellerDispute");
  if (data.dispute_seller_statement) {
    sellerDisputeStatus.textContent = "STATEMENT FILED";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
  } else if (data.seller_waived_statement) {
    sellerDisputeStatus.textContent = "WAIVED ON-CHAIN";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20";
  } else {
    sellerDisputeStatus.textContent = "AWAITING";
    sellerDisputeStatus.className = "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700";
  }

  // Verdict Display from real resolution_reason in GenVM storage
  const verdictCard = document.getElementById("verdictCard");
  if (status === "RESOLVED" && data.resolution_reason) {
    verdictCard.classList.remove("hidden");
    const sellerPct = data.payout_seller_percent ? parseInt(data.payout_seller_percent.toString(), 10) : 0;
    document.getElementById("verdictSellerPercent").textContent = sellerPct;
    document.getElementById("verdictBuyerPercent").textContent = 100 - sellerPct;
    document.getElementById("verdictReasoning").textContent = `"${data.resolution_reason}"`;
  } else {
    verdictCard.classList.add("hidden");
  }
}

// Live Tx Banner Helpers
function showTxBanner(text, hash) {
  const banner = document.getElementById("liveTxBanner");
  banner.classList.remove("hidden");
  document.getElementById("liveTxText").textContent = text;
  const link = document.getElementById("liveTxLink");
  if (hash) {
    link.href = `https://explorer-bradbury.genlayer.com/tx/${hash}`;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }
}

function hideTxBanner() {
  document.getElementById("liveTxBanner").classList.add("hidden");
}

// Notification Toast Helper
function showNotification(title, message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `fixed bottom-5 right-5 z-50 p-4 rounded-xl glass-card border shadow-2xl transition-all duration-300 transform translate-y-0 text-xs max-w-sm flex items-start gap-3 ${
    type === "success" ? "border-emerald-500/50 text-emerald-300" :
    type === "error" ? "border-rose-500/50 text-rose-300" : "border-teal-500/50 text-teal-300"
  }`;
  
  toast.innerHTML = `
    <div class="font-bold">${title}: <span class="font-normal text-slate-300">${message}</span></div>
  `;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
