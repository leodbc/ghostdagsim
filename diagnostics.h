#pragma once

#ifdef GHOSTDAGSIM_DIAGNOSTICS

#include "thirdparty/json.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <sys/resource.h>

namespace ghostdagsim {
namespace diagnostics {

struct Counters {
  uint64_t addblock_calls = 0;
  uint64_t addblock_accepted = 0;
  uint64_t addblock_orphaned = 0;
  uint64_t addblock_parent_refs = 0;
  uint64_t is_blue_refresh_calls = 0;
  uint64_t is_blue_refresh_blocks_scanned = 0;
  uint64_t is_blue_flags_changed = 0;
  uint64_t snapshot_blue_flags_blocks_scanned = 0;
  uint64_t newly_blue_blocks_scanned = 0;
  uint64_t greedy_calls = 0;
  uint64_t greedy_merge_set_candidates = 0;
  uint64_t toposort_calls = 0;
  uint64_t toposort_subset_blocks = 0;
  uint64_t orphan_process_calls = 0;
  uint64_t orphan_entries_scanned = 0;

  uint64_t tx_gen_callbacks_total = 0;
  uint64_t tx_gen_inserted_total = 0;
  uint64_t tx_gen_mempool_full_total = 0;
  uint64_t tx_inv_batches_total = 0;
  uint64_t tx_inv_ids_total = 0;
  uint64_t tx_inv_peer_sends_total = 0;
  uint64_t tx_request_frames_total = 0;
  uint64_t tx_request_ids_total = 0;
  uint64_t tx_response_frames_total = 0;
  uint64_t tx_response_ids_total = 0;
  uint64_t tx_retries_total = 0;
  uint64_t tx_giveups_total = 0;
  uint64_t tx_rx_mempool_full_drops_total = 0;
  uint64_t pending_tx_inv_high_water = 0;
  uint64_t tx_request_queue_high_water = 0;
  uint64_t tx_timeout_queue_high_water = 0;

  uint64_t snapshot_callbacks_total = 0;
  uint64_t snapshot_blocks_scanned_total = 0;

  uint64_t cbor_encode_calls = 0;
  uint64_t cbor_encoded_bytes = 0;
  uint64_t cbor_decode_calls = 0;
  uint64_t cbor_decoded_bytes = 0;
  uint64_t frames_enqueued_total = 0;
  uint64_t modeled_bytes_enqueued_total = 0;

  uint64_t metric_events_total = 0;
  uint64_t metric_json_serialized_bytes = 0;
  uint64_t metric_flush_count = 0;
  uint64_t metric_written_bytes = 0;

  uint64_t is_blue_refresh_ns = 0;
  uint64_t greedy_ns = 0;
  uint64_t toposort_ns = 0;
  uint64_t orphan_scan_ns = 0;
};

struct Identity {
  std::string output_dir;
  std::string scenario;
  uint32_t rank = 0;
  uint32_t mpi_size = 1;
  uint64_t nodes = 0;
  uint64_t miners = 0;
  uint64_t blocks_per_miner = 0;
  double snapshot_interval_seconds = 0.0;
  double tx_generation_interval_seconds = 0.0;
  uint64_t local_nodes = 0;
  uint64_t local_miners = 0;
  uint64_t local_peer_endpoints = 0;
  uint64_t local_miner_peer_endpoints = 0;
};

class Diagnostics {
public:
  static Diagnostics &Get() {
    static Diagnostics instance;
    return instance;
  }

  Counters &counters() { return counters_; }

  void Configure(const Identity &identity) {
    identity_ = identity;
    configured_ = true;
  }

  void MarkSimulationStart() {
    simulation_start_ = Clock::now();
    simulation_started_ = true;
    struct rusage usage {};
    if (getrusage(RUSAGE_SELF, &usage) == 0) {
      start_user_cpu_ns_ = ToNanoseconds(usage.ru_utime);
      start_system_cpu_ns_ = ToNanoseconds(usage.ru_stime);
      cpu_baseline_captured_ = true;
    }
  }

  void MarkSimulationEnd() {
    if (!simulation_started_ || simulation_ended_)
      return;
    simulation_wall_ns_ = static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now() - simulation_start_)
            .count());

    struct rusage usage {};
    if (cpu_baseline_captured_ && getrusage(RUSAGE_SELF, &usage) == 0) {
      const uint64_t end_user = ToNanoseconds(usage.ru_utime);
      const uint64_t end_system = ToNanoseconds(usage.ru_stime);
      user_cpu_ns_ =
          end_user >= start_user_cpu_ns_ ? end_user - start_user_cpu_ns_ : 0;
      system_cpu_ns_ = end_system >= start_system_cpu_ns_
                           ? end_system - start_system_cpu_ns_
                           : 0;
    }
    simulation_ended_ = true;
  }

  void WriteSummary() {
    if (!configured_ || written_)
      return;
    if (simulation_started_ && !simulation_ended_)
      MarkSimulationEnd();
    written_ = true;

    const std::string rank_dir =
        identity_.output_dir + "/rank" + std::to_string(identity_.rank);
    std::error_code ec;
    std::filesystem::create_directories(rank_dir, ec);
    std::ofstream out(rank_dir + "/diagnostics.json",
                      std::ios::out | std::ios::trunc);
    if (!out.is_open())
      return;

    nlohmann::json j;
    j["diagnostic_only"] = true;
    j["schema"] = "ghostdagsim.gateb.diagnostics";
    j["schema_version"] = 1;
    j["build"] = {
        {"diagnostics", true},
        {"instrumentation_base_sha",
         "0af9ac834fec4d60e46fcc7b133d100546cc4476"}};
    j["rank"] = identity_.rank;
    j["mpi_size"] = identity_.mpi_size;
    j["scenario"] = identity_.scenario;
    j["nodes"] = identity_.nodes;
    j["miners"] = identity_.miners;
    j["blocks_per_miner"] = identity_.blocks_per_miner;
    j["snapshot_interval_seconds"] = identity_.snapshot_interval_seconds;
    j["tx_generation_interval_seconds"] =
        identity_.tx_generation_interval_seconds;
    j["topology"] = {
        {"local_nodes", identity_.local_nodes},
        {"local_miners", identity_.local_miners},
        {"local_peer_endpoints", identity_.local_peer_endpoints},
        {"local_miner_peer_endpoints", identity_.local_miner_peer_endpoints}};

#define GHOSTDAGSIM_DIAG_JSON_COUNTER(name) j["counters"][#name] = counters_.name
    GHOSTDAGSIM_DIAG_JSON_COUNTER(addblock_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(addblock_accepted);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(addblock_orphaned);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(addblock_parent_refs);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(is_blue_refresh_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(is_blue_refresh_blocks_scanned);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(is_blue_flags_changed);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(snapshot_blue_flags_blocks_scanned);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(newly_blue_blocks_scanned);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(greedy_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(greedy_merge_set_candidates);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(toposort_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(toposort_subset_blocks);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(orphan_process_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(orphan_entries_scanned);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_gen_callbacks_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_gen_inserted_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_gen_mempool_full_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_inv_batches_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_inv_ids_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_inv_peer_sends_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_request_frames_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_request_ids_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_response_frames_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_response_ids_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_retries_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_giveups_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_rx_mempool_full_drops_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(pending_tx_inv_high_water);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_request_queue_high_water);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(tx_timeout_queue_high_water);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(snapshot_callbacks_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(snapshot_blocks_scanned_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(cbor_encode_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(cbor_encoded_bytes);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(cbor_decode_calls);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(cbor_decoded_bytes);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(frames_enqueued_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(modeled_bytes_enqueued_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(metric_events_total);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(metric_json_serialized_bytes);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(metric_flush_count);
    GHOSTDAGSIM_DIAG_JSON_COUNTER(metric_written_bytes);
#undef GHOSTDAGSIM_DIAG_JSON_COUNTER

    j["timers_ns"] = {
        {"is_blue_refresh", counters_.is_blue_refresh_ns},
        {"greedy_total_including_toposort", counters_.greedy_ns},
        {"toposort", counters_.toposort_ns},
        {"orphan_scan", counters_.orphan_scan_ns}};
    j["process_timing"] = {
        {"simulation_wall_ns", simulation_wall_ns_},
        {"process_cpu_ns", user_cpu_ns_ + system_cpu_ns_},
        {"user_cpu_ns", user_cpu_ns_},
        {"system_cpu_ns", system_cpu_ns_},
        {"interval", "Simulator::Run"}};

    out << j.dump(2) << "\n";
  }

private:
  using Clock = std::chrono::steady_clock;

  Diagnostics() = default;

  static uint64_t ToNanoseconds(const timeval &tv) {
    return static_cast<uint64_t>(tv.tv_sec) * 1000000000ULL +
           static_cast<uint64_t>(tv.tv_usec) * 1000ULL;
  }

  Identity identity_;
  Counters counters_;
  Clock::time_point simulation_start_{};
  uint64_t start_user_cpu_ns_ = 0;
  uint64_t start_system_cpu_ns_ = 0;
  uint64_t simulation_wall_ns_ = 0;
  uint64_t user_cpu_ns_ = 0;
  uint64_t system_cpu_ns_ = 0;
  bool configured_ = false;
  bool simulation_started_ = false;
  bool simulation_ended_ = false;
  bool cpu_baseline_captured_ = false;
  bool written_ = false;
};

class ScopedTimer {
public:
  explicit ScopedTimer(uint64_t &accumulator)
      : accumulator_(accumulator), start_(Clock::now()) {}
  ~ScopedTimer() {
    accumulator_ += static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now() - start_)
            .count());
  }

private:
  using Clock = std::chrono::steady_clock;
  uint64_t &accumulator_;
  Clock::time_point start_;
};

} // namespace diagnostics
} // namespace ghostdagsim

#define GHOSTDAGSIM_DIAG_CAT_INNER(a, b) a##b
#define GHOSTDAGSIM_DIAG_CAT(a, b) GHOSTDAGSIM_DIAG_CAT_INNER(a, b)
#define DIAG_INC(field)                                                        \
  do {                                                                         \
    ++::ghostdagsim::diagnostics::Diagnostics::Get().counters().field;          \
  } while (0)
#define DIAG_ADD(field, value)                                                 \
  do {                                                                         \
    ::ghostdagsim::diagnostics::Diagnostics::Get().counters().field +=          \
        static_cast<uint64_t>(value);                                          \
  } while (0)
#define DIAG_HIGH_WATER(field, value)                                          \
  do {                                                                         \
    const uint64_t GHOSTDAGSIM_DIAG_CAT(_diag_value_, __LINE__) =              \
        static_cast<uint64_t>(value);                                          \
    auto &GHOSTDAGSIM_DIAG_CAT(_diag_counter_, __LINE__) =                     \
        ::ghostdagsim::diagnostics::Diagnostics::Get().counters().field;        \
    GHOSTDAGSIM_DIAG_CAT(_diag_counter_, __LINE__) =                           \
        std::max(GHOSTDAGSIM_DIAG_CAT(_diag_counter_, __LINE__),               \
                 GHOSTDAGSIM_DIAG_CAT(_diag_value_, __LINE__));                \
  } while (0)
#define DIAG_TIMER(field)                                                      \
  ::ghostdagsim::diagnostics::ScopedTimer                                      \
      GHOSTDAGSIM_DIAG_CAT(_diag_timer_, __LINE__)(                            \
          ::ghostdagsim::diagnostics::Diagnostics::Get().counters().field)

#else

#define DIAG_INC(field) do { } while (0)
#define DIAG_ADD(field, value) do { } while (0)
#define DIAG_HIGH_WATER(field, value) do { } while (0)
#define DIAG_TIMER(field) do { } while (0)

#endif
