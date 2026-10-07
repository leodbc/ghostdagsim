/**
 * @file dag.cc
 * @brief Ghostdag consensus protocol implementation
 * @author Eduardo Lechinski Ramos <lechinski@univali.br>
 * @date 2026
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation;
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 */

#include "dag.h"
#include "diagnostics.h"
#include "metrics.h"

#include <algorithm>
#include <cstdint>
#include <queue>

// ---------------------------------------------------------------------------
// Shared block bodies
// ---------------------------------------------------------------------------

namespace {
std::unordered_map<uint64_t, std::shared_ptr<const TxSet>> &BodyTable() {
  static std::unordered_map<uint64_t, std::shared_ptr<const TxSet>> table;
  return table;
}

uint64_t TxChecksum(const TxSet &txs) {
  uint64_t c = 0;
  for (const auto &tx : txs)
    c ^= tx.tx_id;
  return c;
}
} // namespace

const std::shared_ptr<const TxSet> &BlockBodyStore::Empty() {
  static const std::shared_ptr<const TxSet> empty = std::make_shared<TxSet>();
  return empty;
}

std::shared_ptr<const TxSet> BlockBodyStore::Intern(uint64_t block_id,
                                                    TxSet &&txs) {
  auto &table = BodyTable();
  auto it = table.find(block_id);
  if (it != table.end()) {
    // Same block id, same transaction ids: reuse. Anything else keeps a
    // private copy so a divergent body can never leak between nodes.
    if (it->second->size() == txs.size() &&
        TxChecksum(*it->second) == TxChecksum(txs))
      return it->second;
    return std::make_shared<const TxSet>(std::move(txs));
  }
  auto body = std::make_shared<const TxSet>(std::move(txs));
  table.emplace(block_id, body);
  return body;
}

void BlockBodyStore::Clear() { BodyTable().clear(); }

// ---------------------------------------------------------------------------
// Blockchain
// ---------------------------------------------------------------------------

Blockchain::Blockchain(int k, uint64_t node_id)
    : ghostdag_k(k), next_block_id(1), node_id_metric(node_id) {
  Block genesis;
  genesis.header.block_id = 0;
  genesis.header.miner_id = -1;
  genesis.header.time_created = 0.0;
  genesis.time_received = 0.0;
  genesis.size_in_bytes = 0;
  genesis.blue_score = 1;
  genesis.is_blue = true;
  blocks[genesis.header.block_id] = genesis;
  tips.insert(genesis.header.block_id);

  idx_of_[0] = 0;
  id_of_.push_back(0);
  past_.emplace_back();
  BitSet blue;
  blue.set(0);
  blue_.push_back(std::move(blue));
}

uint32_t Blockchain::Index(uint64_t block_id) const {
  auto it = idx_of_.find(block_id);
  __ASSERT__(it != idx_of_.end(), "block is not in the DAG");
  return it->second;
}

std::set<uint64_t> Blockchain::GetPast(uint64_t block_id) const {
  std::set<uint64_t> past;
  auto it = idx_of_.find(block_id);
  if (it == idx_of_.end())
    return past;
  past_[it->second].for_each([&](size_t i) { past.insert(id_of_[i]); });
  return past;
}

std::set<uint64_t> Blockchain::GetFuture(uint64_t block_id) const {
  std::set<uint64_t> future;
  std::queue<uint64_t> q;
  auto ci = children.find(block_id);
  if (ci != children.end())
    for (uint64_t c : ci->second) {
      future.insert(c);
      q.push(c);
    }

  while (!q.empty()) {
    uint64_t cur = q.front();
    q.pop();
    auto ci2 = children.find(cur);
    if (ci2 == children.end())
      continue;
    for (uint64_t c : ci2->second)
      if (!future.count(c)) {
        future.insert(c);
        q.push(c);
      }
  }
  return future;
}

std::set<uint64_t> Blockchain::BlueSet(uint64_t block_id) const {
  std::set<uint64_t> blue;
  auto it = idx_of_.find(block_id);
  if (it == idx_of_.end())
    return blue;
  blue_[it->second].for_each([&](size_t i) { blue.insert(id_of_[i]); });
  return blue;
}

bool Blockchain::InBlueSet(uint64_t block_id, uint64_t member) const {
  auto b = idx_of_.find(block_id);
  auto m = idx_of_.find(member);
  if (b == idx_of_.end() || m == idx_of_.end())
    return false;
  return blue_[b->second].test(m->second);
}

bool Blockchain::InPast(uint64_t block_id, uint64_t ancestor) const {
  auto b = idx_of_.find(block_id);
  auto a = idx_of_.find(ancestor);
  if (b == idx_of_.end() || a == idx_of_.end())
    return false;
  return past_[b->second].test(a->second);
}

// Kahn over an arbitrary subset. Ready blocks are taken in ascending id order
// so the greedy pass below is deterministic.
std::vector<uint64_t> Blockchain::TopologicalSort(const BitSet &subset) const {
  DIAG_INC(toposort_calls);
  DIAG_TIMER(toposort_ns);
  std::vector<uint64_t> ids;
  subset.for_each([&](size_t i) { ids.push_back(id_of_[i]); });
  DIAG_ADD(toposort_subset_blocks, ids.size());
  std::sort(ids.begin(), ids.end());

  std::map<uint64_t, uint64_t> indeg;
  for (uint64_t b : ids) {
    uint64_t d = 0;
    for (uint64_t p : blocks.at(b).header.parent_hashes) {
      auto pi = idx_of_.find(p);
      if (pi != idx_of_.end() && subset.test(pi->second))
        ++d;
    }
    indeg[b] = d;
  }
  std::queue<uint64_t> q;
  for (auto &[b, d] : indeg)
    if (d == 0)
      q.push(b);

  std::vector<uint64_t> result;
  result.reserve(ids.size());
  while (!q.empty()) {
    uint64_t cur = q.front();
    q.pop();
    result.push_back(cur);
    auto ci = children.find(cur);
    if (ci != children.end())
      for (uint64_t ch : ci->second) {
        auto chi = idx_of_.find(ch);
        if (chi != idx_of_.end() && subset.test(chi->second) &&
            --indeg[ch] == 0)
          q.push(ch);
      }
  }
  return result;
}

// GreedyBlueSet – GHOSTDAG algorithm
//
// Steps:
//   1. Selected parent (sp) = parent with highest blue_score (lower id wins
//   ties); chosen by the caller.
//   2. Inherit sp.blue_set as the starting blue set.
//   3. Merge set = past(block) \ ( past(sp) ∪ {sp} ).
//   4. Process merge set in topological order.  For candidate C:
//        anticone_blues = |{ b ∈ blue : neither b∈past(C) nor C∈past(b) }|
//        If anticone_blues ≤ k  →  add C to blue.
//   5. block is always blue (all blue blocks are in its past → anticone = 0).
BitSet Blockchain::GreedyBlueSet(uint32_t idx, uint32_t sp_idx,
                                 const BitSet &past) const {
  DIAG_INC(greedy_calls);
  DIAG_TIMER(greedy_ns);
  BitSet blue = blue_[sp_idx];

  BitSet merge_set = past.and_not(past_[sp_idx]);
  merge_set.reset(sp_idx);

#ifdef GHOSTDAGSIM_DIAGNOSTICS
  auto ordered_merge_set = TopologicalSort(merge_set);
  DIAG_ADD(greedy_merge_set_candidates, ordered_merge_set.size());
  for (uint64_t candidate : ordered_merge_set) {
#else
  for (uint64_t candidate : TopologicalSort(merge_set)) {
#endif
    uint32_t ci = idx_of_.at(candidate);
    const BitSet &past_cand = past_[ci];
    uint64_t anticone_blues = 0;
    // Blue blocks outside past(C); those with C outside their past are C's
    // blue anticone.
    blue.for_each_and_not(past_cand, [&](size_t b) {
      if (!past_[b].test(ci))
        if (++anticone_blues > (uint64_t)ghostdag_k)
          return false;
      return true;
    });
    if (anticone_blues <= (uint64_t)ghostdag_k)
      blue.set(ci);
  }

  blue.set(idx);
  return blue;
}

void Blockchain::AddBlock(const Block &new_block) {
  DIAG_INC(addblock_calls);
  DIAG_ADD(addblock_parent_refs, new_block.header.parent_hashes.size());
  uint64_t block_id = new_block.header.block_id;

  // Orphan check
  for (uint64_t p : new_block.header.parent_hashes) {
    if (!blocks.count(p)) {
      DIAG_INC(addblock_orphaned);
      orphans[block_id] = new_block;
      return;
    }
  }

  // Insert
  DIAG_INC(addblock_accepted);
  Block &blk = blocks[block_id];
  blk = new_block;
  uint32_t idx = static_cast<uint32_t>(id_of_.size());
  idx_of_[block_id] = idx;
  id_of_.push_back(block_id);

  BitSet past;
  for (uint64_t p : new_block.header.parent_hashes) {
    uint32_t pi = idx_of_.at(p);
    past |= past_[pi];
    past.set(pi);
  }
  past_.push_back(past);

  for (uint64_t p : new_block.header.parent_hashes) {
    children[p].insert(block_id);
    tips.erase(p);
  }
  tips.insert(block_id);

  // Selected parent: highest blue score, lower id breaks ties.
  std::optional<uint64_t> sp_u;
  std::optional<uint64_t> max_sp_u;
  for (uint64_t p : new_block.header.parent_hashes) {
    uint64_t s = blocks.at(p).blue_score;
    if (!max_sp_u.has_value() || s > max_sp_u || (s == max_sp_u && p < sp_u)) {
      max_sp_u = s;
      sp_u = p;
    }
  }

  BitSet blue;
  if (sp_u.has_value()) {
    blue = GreedyBlueSet(idx, idx_of_.at(sp_u.value()), past);
    blk.selected_parent = sp_u.value();
  } else {
    blue.set(idx); // no parents: only itself
  }
  // blue_score = |past ∩ blue| + 1 (the block itself)
  blk.blue_score = past.count_and(blue) + 1;
  blue_.push_back(std::move(blue));

  // Re-evaluate is_blue for ALL accepted blocks.
  // is_blue = "this block is in the current selected tip's blue_set".
  // We must update every block – not just current tips – because when a merge
  // block is added, previously non-tip blocks (now merged) need updating too.
#ifdef GHOSTDAGSIM_DIAGNOSTICS
  {
    DIAG_INC(is_blue_refresh_calls);
    DIAG_TIMER(is_blue_refresh_ns);
    std::optional<uint64_t> sel_tip = SelectTip();
    if (sel_tip.has_value()) {
      const BitSet &tip_blue = blue_[idx_of_.at(sel_tip.value())];
      for (auto &[id, b] : blocks) {
        DIAG_INC(is_blue_refresh_blocks_scanned);
        bool is_blue = tip_blue.test(idx_of_.at(id));
        if (b.is_blue != is_blue)
          DIAG_INC(is_blue_flags_changed);
        b.is_blue = is_blue;
      }
    }
  }
#else
  std::optional<uint64_t> sel_tip = SelectTip();
  if (sel_tip.has_value()) {
    const BitSet &tip_blue = blue_[idx_of_.at(sel_tip.value())];
    for (auto &[id, b] : blocks)
      b.is_blue = tip_blue.test(idx_of_.at(id));
  }
#endif

  ProcessOrphans();
}

void Blockchain::ProcessOrphans() {
  DIAG_INC(orphan_process_calls);
  bool progress = true;
  while (progress) {
    progress = false;
    std::vector<uint64_t> ready;
    {
      // Time only the orphan scan. AddBlock() below may recurse into
      // ProcessOrphans(), so timing the whole function would double-count
      // GHOSTDAG work and nested orphan processing.
      DIAG_TIMER(orphan_scan_ns);
      for (auto &[oid, oblk] : orphans) {
        DIAG_INC(orphan_entries_scanned);
        bool can_add = true;
        for (uint64_t p : oblk.header.parent_hashes)
          if (!blocks.count(p)) {
            can_add = false;
            break;
          }
        if (can_add)
          ready.push_back(oid);
      }
    }
    for (uint64_t oid : ready) {
      auto it = orphans.find(oid);
      if (it == orphans.end())
        continue;

      Block ob = it->second;
      orphans.erase(it);
      AddBlock(ob);

      progress = true;
    }
  }
}

std::optional<uint64_t> Blockchain::SelectTip() const {
  if (tips.empty())
    return std::nullopt;

  std::optional<uint64_t> best;
  std::optional<uint64_t> best_score;
  for (uint64_t t : tips) {
    uint64_t s = blocks.at(t).blue_score;
    if (!best_score.has_value() || s > best_score ||
        (s == best_score && t < best)) {
      best_score = s;
      best = t;
    }
  }
  return best;
}

// ComputeGHOSTDAGOrdering
// Primary:   higher blue_score first
// Secondary: earlier time_created first
// Tertiary:  lower block_id first
std::vector<uint64_t> Blockchain::ComputeGHOSTDAGOrdering() const {
  std::map<uint64_t, uint64_t> indeg;
  for (auto &[id, blk] : blocks) {
    indeg[id] = 0;
    for (uint64_t p : blk.header.parent_hashes)
      if (blocks.count(p))
        ++indeg[id];
  }

  auto cmp = [this](uint64_t a, uint64_t b) {
    const Block &ba = blocks.at(a);
    const Block &bb = blocks.at(b);
    if (ba.blue_score != bb.blue_score)
      return ba.blue_score < bb.blue_score;
    if (ba.header.time_created != bb.header.time_created)
      return ba.header.time_created > bb.header.time_created;
    return a > b;
  };
  std::priority_queue<uint64_t, std::vector<uint64_t>, decltype(cmp)> pq(cmp);
  for (auto &[id, d] : indeg)
    if (d == 0)
      pq.push(id);

  std::vector<uint64_t> ordering;
  ordering.reserve(blocks.size());
  while (!pq.empty()) {
    uint64_t cur = pq.top();
    pq.pop();
    ordering.push_back(cur);
    auto ci = children.find(cur);
    if (ci != children.end())
      for (uint64_t ch : ci->second)
        if (--indeg[ch] == 0)
          pq.push(ch);
  }
  return ordering;
}

bool Blockchain::IsKCluster(const std::set<uint64_t> &blue_set) const {
  for (uint64_t b : blue_set) {
    auto bi = idx_of_.find(b);
    if (bi == idx_of_.end())
      return false;
    uint64_t ac = 0;
    for (uint64_t x : blue_set) {
      if (x == b)
        continue;
      auto xi = idx_of_.find(x);
      if (xi == idx_of_.end())
        return false;
      bool x_in_past_b = past_[bi->second].test(xi->second);
      bool x_in_future_b = past_[xi->second].test(bi->second);
      if (!x_in_past_b && !x_in_future_b)
        if (++ac > (uint64_t)ghostdag_k)
          return false;
    }
  }
  return true;
}

bool Blockchain::IsKClusterSubset(const std::set<uint64_t> &blue_set) const {
  std::set<uint64_t> existing;
  for (uint64_t b : blue_set)
    if (blocks.count(b))
      existing.insert(b);
  return IsKCluster(existing);
}

std::vector<bool> Blockchain::SnapshotBlueFlags() const {
  std::vector<bool> flags(id_of_.size(), false);
  for (size_t i = 0; i < id_of_.size(); i++) {
    DIAG_INC(snapshot_blue_flags_blocks_scanned);
    flags[i] = blocks.at(id_of_[i]).is_blue;
  }
  return flags;
}

std::vector<uint64_t>
Blockchain::NewlyBlue(const std::vector<bool> &before) const {
  std::vector<uint64_t> out;
  for (size_t i = 0; i < id_of_.size(); i++) {
    DIAG_INC(newly_blue_blocks_scanned);
    bool prev = i < before.size() && before[i];
    if (!prev && blocks.at(id_of_[i]).is_blue)
      out.push_back(id_of_[i]);
  }
  std::sort(out.begin(), out.end());
  return out;
}

uint64_t Blockchain::GetDagWidth() const { return tips.size(); }

bool Blockchain::HasBlock(uint64_t id) const { return blocks.count(id) > 0; }
bool Blockchain::IsRed(uint64_t id) const {
  auto it = blocks.find(id);
  return it != blocks.end() && !it->second.is_blue;
}
bool Blockchain::IsOrphan(uint64_t id) const { return orphans.count(id) > 0; }
