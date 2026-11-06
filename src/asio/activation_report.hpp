#pragma once
#include "windows/worker_process.hpp"
#include <string>

namespace sl3::asio {
// Controller ownership only. Even complete controller retirement is not a
// physical USB release/readiness attestation for its nested native worker.
struct BrokerActivationReport {
    bool attempted=false,ready=false,stop_requested=false,retirement_deferred=false;
    bool termination_requested=false;
    worker::ProcessState controller;
    std::string cleanup_error;
};
inline bool activation_controller_retired(const BrokerActivationReport& report) noexcept {
    return report.cleanup_error.empty() && (!report.controller.started ||
        (report.controller.process_exited && report.controller.job_empty));
}
inline bool activation_cleanup_contained(const BrokerActivationReport& report) noexcept {
    return report.termination_requested || !activation_controller_retired(report);
}
inline const char* activation_failure_message(const BrokerActivationReport& report) noexcept {
    if(!activation_controller_retired(report))
        return "SL3 transport startup failed; controller cleanup is unverified. Check session diagnostics before retrying.";
    if(report.termination_requested)
        return "SL3 transport startup failed; controller cleanup was forced. Check session diagnostics before retrying.";
    return "SL3 transport activation failed before readiness. See session diagnostics; USB readiness is not established.";
}
}
