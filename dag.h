/**
 * @file dag.h
 * @brief Ghostdag consensus protocol definition and core structures
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

#pragma once

#include "ns3/ipv4-address.h"
#include "ns3/simulator.h"

#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <unordered_map>
#include <vector>

#define NOW ns3::Simulator::Now().GetSeconds()
#define NID (GetNode()->GetId())
#define IPV4_STR(from)                                                         \
  ([&]() {                                                                     \
    std::stringstream ss;                                                      \
    InetSocketAddress::ConvertFrom((from)).GetIpv4().Print(ss);                \
    return ss.str();                                                           \
  }())
inline void __ASSERT_HANDLE(const char *expression, const char *file, int line,
                            const char *message = nullptr) {
  std::cerr << "Assertion Failed Error!\n";
  std::cerr << "  Expression: [" << expression << "]\n";
  std::cerr << "  File:       " << file << "\n";
  std::cerr << "  Line:       " << line << "\n";
  if (message) {
    std::cerr << "  Message:    " << message << "\n";
  }

  std::abort();
}
#define __ASSERT__(expr, msg)                                                  \
  do {                                                                         \
    if (!(expr)) {                                                             \
      __ASSERT_HANDLE(#expr, __FILE__, __LINE__, msg);                         \
    }                                                                          \
  } while (false)

typedef struct {
  double download_speed;
  double upload_speed;
} NodeInternetSpeeds;

enum Region {
  NORTH_AMERICA,
  EUROPE,
  SOUTH_AMERICA,
  ASIA_PACIFIC,
  JAPAN,
  AUSTRALIA,
  OTHER
};

enum Messages {
  NO_MESSAGE,
  PING,
  PONG,

  REQ_HEADERS,
  BLOCK_HEADERS,

  INV_RELAY_BLOCK,
  REQ_RELAY_BLOCK,

  BLOCK,

  GRAPHENE_BLOCK,
  GRAPHENE_RECOVERY_REQUEST,
  GRAPHENE_RECOVERY_RESPONSE,

  INV_TRANSACTIONS,
  REQ_TRANSACTIONS,
  TRANSACTIONS,
};

inline static std::string GetMessageName(Messages msg) {
  switch (msg) {
  case NO_MESSAGE:
    return "NO_MESSAGE";
  case PING:
    return "PING";
  case PONG:
    return "PONG";
  case REQ_HEADERS:
    return "REQ_HEADERS";
  case BLOCK_HEADERS:
    return "BLOCK_HEADERS";
  case INV_RELAY_BLOCK:
    return "INV_RELAY_BLOCK";
  case REQ_RELAY_BLOCK:
    return "REQ_RELAY_BLOCK";
  case BLOCK:
    return "BLOCK";
  case GRAPHENE_BLOCK:
    return "GRAPHENE_BLOCK";
  case GRAPHENE_RECOVERY_REQUEST:
    return "GRAPHENE_RECOVERY_REQUEST";
  case GRAPHENE_RECOVERY_RESPONSE:
    return "GRAPHENE_RECOVERY_RESPONSE";
  case INV_TRANSACTIONS:
    return "INV_TRANSACTIONS";
  case REQ_TRANSACTIONS:
    return "REQ_TRANSACTIONS";
  case TRANSACTIONS:
    return "TRANSACTIONS";
  default:
    return "UNKNOWN_MESSAGE";
  }
}

struct Transaction {
  uint64_t tx_id;
  uint64_t size_bytes;
  uint32_t fee = 0;

  bool operator<(const Transaction &other) const { return tx_id < other.tx_id; }
};

using TxSet = std::set<Transaction>;

/**
 * Block bodies are immutable once mined and every node ends up holding the
 * same transaction set for a given block id, so nodes hosted by the same
 * process share one copy instead of each keeping a private one.
 */
class BlockBodyStore {
public:
  static std::shared_ptr<const TxSet> Intern(uint64_t block_id, TxSet &&txs);
  static const std::shared_ptr<const TxSet> &Empty();
  static void Clear();
};

struct BlockHeader {
  uint64_t block_id;
  uint64_t miner_id;
  double time_created;
  std::vector<uint64_t> parent_hashes;

  BlockHeader() : block_id(0), miner_id(0), time_created(0) {}

  int GetSizeInBytes() const {
    int base_size = 80;
    int parent_size = parent_hashes.size() * 32;

    int varint_size = 1;
    if (parent_hashes.size() >= 253) {
      varint_size = 3;
    }

    return base_size + varint_size + parent_size;
  }
};

struct Block {
  BlockHeader header;
  std::shared_ptr<const TxSet> txs;
  int size_in_bytes;

  double time_received;
  ns3::Ipv4Address received_from;
  uint64_t blue_score;
  bool is_blue;
  uint64_t selected_parent;

  Block()
      : txs(BlockBodyStore::Empty()), size_in_bytes(0), time_received(0),
        blue_score(0), is_blue(false), selected_parent(-1) {}

  const TxSet &transactions() const { return *txs; }
  size_t tx_count() const { return txs->size(); }

  int GetTotalSize() const {
    int body_size = tx_count() * 4;
    return header.GetSizeInBytes() + body_size;
  }
};

/**
 * Dense bit set over block indices. Every accepted block gets an index in
 * insertion order, so per-block ancestor and blue sets cost n/8 bytes each
 * instead of a tree node per member.
 */
class BitSet {
public:
  bool test(size_t i) const {
    size_t w = i >> 6;
    return w < words_.size() && ((words_[w] >> (i & 63)) & 1u);
  }
  void set(size_t i) {
    size_t w = i >> 6;
    if (w >= words_.size())
      words_.resize(w + 1, 0);
    words_[w] |= uint64_t{1} << (i & 63);
  }
  void reset(size_t i) {
    size_t w = i >> 6;
    if (w < words_.size())
      words_[w] &= ~(uint64_t{1} << (i & 63));
  }
  BitSet &operator|=(const BitSet &o) {
    if (o.words_.size() > words_.size())
      words_.resize(o.words_.size(), 0);
    for (size_t i = 0; i < o.words_.size(); i++)
      words_[i] |= o.words_[i];
    return *this;
  }
  size_t count() const {
    size_t c = 0;
    for (uint64_t w : words_)
      c += __builtin_popcountll(w);
    return c;
  }
  size_t count_and(const BitSet &o) const {
    size_t n = std::min(words_.size(), o.words_.size());
    size_t c = 0;
    for (size_t i = 0; i < n; i++)
      c += __builtin_popcountll(words_[i] & o.words_[i]);
    return c;
  }
  // this & ~o
  BitSet and_not(const BitSet &o) const {
    BitSet r;
    r.words_.resize(words_.size());
    for (size_t i = 0; i < words_.size(); i++)
      r.words_[i] = words_[i] & (i < o.words_.size() ? ~o.words_[i] : ~uint64_t{0});
    return r;
  }
  // Calls f(index) for every set bit, in ascending index order.
  template <typename F> void for_each(F f) const {
    for (size_t wi = 0; wi < words_.size(); wi++) {
      uint64_t w = words_[wi];
      while (w) {
        size_t bit = __builtin_ctzll(w);
        f((wi << 6) + bit);
        w &= w - 1;
      }
    }
  }
  // Calls f(index) for every bit set in this and clear in o; stops when f
  // returns false.
  template <typename F> void for_each_and_not(const BitSet &o, F f) const {
    for (size_t wi = 0; wi < words_.size(); wi++) {
      uint64_t w = words_[wi] & (wi < o.words_.size() ? ~o.words_[wi] : ~uint64_t{0});
      while (w) {
        size_t bit = __builtin_ctzll(w);
        if (!f((wi << 6) + bit))
          return;
        w &= w - 1;
      }
    }
  }
  bool empty() const {
    for (uint64_t w : words_)
      if (w)
        return false;
    return true;
  }

private:
  std::vector<uint64_t> words_;
};

struct Blockchain {
  Blockchain(int k = 0, uint64_t node_id = 0);
  virtual ~Blockchain() {}

  int ghostdag_k;
  uint64_t next_block_id;
  uint64_t node_id_metric;
  std::set<uint64_t> tips;
  std::map<uint64_t, std::set<uint64_t>> children;
  std::map<uint64_t, Block> blocks;
  std::map<uint64_t, Block> orphans;

  uint64_t GetDagWidth() const;
  bool HasBlock(uint64_t block_id) const;
  bool IsRed(uint64_t block_id) const;
  bool IsOrphan(uint64_t block_id) const;

  void AddBlock(const Block &new_block);

  // Set views of the internal bit sets; meant for tests and diagnostics.
  std::set<uint64_t> GetPast(uint64_t block_id) const;
  std::set<uint64_t> GetFuture(uint64_t block_id) const;
  std::set<uint64_t> BlueSet(uint64_t block_id) const;
  bool InBlueSet(uint64_t block_id, uint64_t member) const;
  bool InPast(uint64_t block_id, uint64_t ancestor) const;

  bool IsKCluster(const std::set<uint64_t> &blue_set) const;
  bool IsKClusterSubset(const std::set<uint64_t> &blue_set) const;

  std::optional<uint64_t> SelectTip() const;
  std::vector<uint64_t> ComputeGHOSTDAGOrdering() const;

  // is_blue flags indexed by insertion order, and the ids (ascending) of the
  // blocks that are blue now but were not in the snapshot.
  std::vector<bool> SnapshotBlueFlags() const;
  std::vector<uint64_t> NewlyBlue(const std::vector<bool> &before) const;

private:
  std::unordered_map<uint64_t, uint32_t> idx_of_;
  std::vector<uint64_t> id_of_;
  std::vector<BitSet> past_;
  std::vector<BitSet> blue_;

  uint32_t Index(uint64_t block_id) const;
  BitSet GreedyBlueSet(uint32_t idx, uint32_t sp_idx, const BitSet &past) const;
  std::vector<uint64_t> TopologicalSort(const BitSet &subset) const;
  void ProcessOrphans();
};
