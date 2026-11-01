#pragma once
#include "windows/process_wait.hpp"

namespace sl3::worker {
struct BrokerBinding {
    std::wstring endpoint;
    std::shared_ptr<ProcessWait> server;
    std::shared_ptr<const void> files;
};
// Pure current-process record formatter. Publication is a separate explicit
// controller action. It does not create an endpoint, process or device lease.
std::string broker_record_text(const std::wstring& endpoint,const std::string& worker_sha256);
// Immutable, hash-pinned record and image; exact live process creation identity.
// This checks on-disk consistency, not in-memory code attestation or a sandbox.
BrokerBinding bind_broker_record(const std::filesystem::path& record,const std::string& record_sha256,
    const std::filesystem::path& broker_image,const std::string& broker_sha256,const std::string& worker_sha256);
}
