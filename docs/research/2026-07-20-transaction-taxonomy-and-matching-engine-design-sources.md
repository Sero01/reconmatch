# Transaction Taxonomy and Matching Engine — Source Register

> Research date: 2026-07-20. Normative sources define financial-domain semantics; papers establish algorithmic properties. A matching implementation must still be tested against its own data distributions and financial-control policy.

| ID | Source | Type | Claim supported |
|---|---|---|---|
| T01 | [ISO 20022 business areas](https://www.iso20022.org/sites/default/files/documents/D7/ISO20022_BusinessAreas.pdf) | International standard | Payment initiation, clearing/settlement, cash management, remittance, trade services, and their status/exception semantics are distinct business domains. |
| T02 | [ISO 20022 repository and business model](https://www.iso20022.org/iso20022-repository/business-model) | International standard | Common business concepts span payments, securities, trade services, FX, cards, and related services. |
| T03 | [ISO 20022 catalogue](https://www.iso20022.org/catalogue-messages) | International standard | Message definitions, schemas, and usage guidance are versioned artefacts. |
| T04 | [ISO 15022 message categories](https://www.iso20022.org/15022/uhb) | Industry standard | Securities operations include allocation, confirmation, settlement, position, holdings, pending transactions, lending, collateral, and corporate-action messages. |
| T05 | [Swift settlement and reconciliation](https://www.swift.com/securities/settlement-and-reconciliation) | Market infrastructure | Settlement reconciliation includes status, movement, holdings, pending instructions, custodians, CSDs, CCPs, and T+1/T+0 pressure. |
| T06 | [Nacha reversals and enforcement](https://www.nacha.org/rules/reversals-and-enforcement) | Payment-network rules | ACH reversals/returns are lifecycle events with constrained reasons, formats, and time windows—not independent payments. |
| T07 | [Swift ISO 20022 user handbook](https://www.swift.com/swift-resource/251967/download) | Market infrastructure | Payment statuses express operational state and must be retained as part of transaction lifecycle. |
| A01 | [Kuhn, *The Hungarian Method for the Assignment Problem* (1955)](https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/nav.3800020109) | Primary research | Linear one-to-one assignment maximizes/minimizes a total score/cost subject to one-use constraints. |
| A02 | [Jonker & Volgenant, shortest augmenting-path assignment (1987)](https://doi.org/10.1007/BF02278710) | Primary research | Efficient sparse/dense linear-assignment algorithm using shortest paths. |
| A03 | [Chen et al., subset sum (2023)](https://arxiv.org/abs/2301.07134) | Primary research | Exact subset-sum remains exponential in worst case; classical meet-in-the-middle is approximately `O(2^(n/2))`. |
| A04 | [Bertsekas, *Linear Network Optimization*](https://www.mit.edu/~dimitrib/net.html) | Primary technical text | Assignment, min-cost flow, and shortest-path methods are related network-optimization formulations. |
| A05 | [Michelson & Knoblock, blocking schemes (2006)](https://cdn.aaai.org/AAAI/2006/AAAI06-070.pdf) | Primary research | Blocking reduces impractical all-pairs record comparison to a candidate set; candidate recall versus reduction is the key trade-off. |
| A06 | [Fellegi & Sunter, record-linkage theory (1969)](https://doi.org/10.1080/01621459.1969.10501049) | Primary research | Probabilistic linkage distinguishes matches/non-matches from comparison evidence and error costs. |
| A07 | [Albutiu, Kemper & Neumann, massively parallel sort-merge joins (2012)](https://arxiv.org/abs/1207.0145) | Primary research | Partitioned, parallel sort-merge joins can scale near-linearly on large in-memory multi-core data. |
| A08 | [Yi, join algorithms from external memory to BSP (2018)](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ICDT.2018.2) | Primary research | Large joins depend on memory/I/O/distributed execution model, not only comparison count. |

## Interpretation rule

Use T01–T07 to decide what a transaction state or business identifier means. Use A01–A08 to choose an algorithmic family. Neither category determines business policy: auto-match thresholds, materiality, tolerances, and permissible netting require explicit owner approval and empirical validation.
