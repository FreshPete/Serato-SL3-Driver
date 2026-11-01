#include "core/capture.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class F> void rejects(F call) { bool caught = false; try { call(); } catch (const std::runtime_error&) { caught = true; } require(caught, "Expected rejection"); }
struct Fake final : sl3::CaptureBackend {
    std::vector<std::string> events;
    std::array<bool, 4> pending{}, canceled{};
    int fail_prepare = -1, fail_submit = -1, failed_completion = -1, stuck = -1, fail_release = -1;
    bool cancel_throws=false;
    mutable std::uint64_t clock = 0;
    void prepare(std::size_t i) override { if (int(i) == fail_prepare) throw std::runtime_error("prepare failure"); events.push_back("prepare" + std::to_string(i)); }
    void submit(std::size_t i, bool next) override {
        require(next == (i != 0), "Continuity flag wrong");
        if (int(i) == fail_submit) throw std::runtime_error("submit failure");
        pending[i] = true; events.push_back("submit" + std::to_string(i));
    }
    sl3::Completion wait(std::size_t i, std::uint32_t timeout) override {
        events.push_back("wait" + std::to_string(i));
        if (int(i) == stuck) { clock += timeout; return sl3::Completion::pending; }
        pending[i] = false;
        return canceled[i] || int(i) == failed_completion ? sl3::Completion::failure : sl3::Completion::success;
    }
    void cancel(std::size_t i) override { if(cancel_throws) throw std::runtime_error("cancel failure"); canceled[i] = true; events.push_back("cancel" + std::to_string(i)); }
    void release(std::size_t i) override { require(!pending[i], "Released pending memory"); if(int(i)==fail_release) throw std::runtime_error("release failure"); events.push_back("release" + std::to_string(i)); }
    std::uint64_t now_ms() const override { return clock; }
};

int main() {
    try {
        // Padding deliberately contains nonzero bytes. Only returned slices count.
        std::vector<std::uint8_t> buffer(252, 0x5a);
        const std::array<std::int32_t, 6> values{-8388608, -1, 0, 1, 0x123456, 8388607};
        for (std::size_t c = 0; c < 6; ++c) for (std::size_t byte = 0; byte < 3; ++byte)
            buffer[126 + c * 3 + byte] = std::uint8_t(std::uint32_t(values[c]) >> (byte * 8));
        auto decoded = sl3::decode_capture(buffer, {{0, 0, 0}, {126, 18, 0}});
        require(decoded.frames.size() == 1 && decoded.frames[0] == values && decoded.packed_pcm.size() == 18 && decoded.zero_packets == 1, "Padding/sample decode failure");
        rejects([&] { sl3::decode_capture(buffer, {{0, 17, 0}}); });
        rejects([&] { sl3::decode_capture(buffer, {{240, 18, 0}}); });
        rejects([&] { sl3::decode_capture(buffer, {{0, 18, 0}, {9, 18, 0}}); });
        rejects([&] { sl3::decode_capture(buffer, {{0, 18, 0xc0000001}}); });
        rejects([&] { sl3::decode_capture(buffer, {{0xffffffff, 18, 0}}); });
        Fake ok; auto success = sl3::capture_transaction(ok);
        require(success.transfers_succeeded && success.cleanup_complete, "Success transaction failed");
        Fake preparation; preparation.fail_prepare = 2; auto p = sl3::capture_transaction(preparation);
        require(!p.transfers_succeeded && p.cleanup_complete && preparation.events.back() == "release1", "Prepare failure cleanup");
        Fake submission; submission.fail_submit = 2; auto s = sl3::capture_transaction(submission);
        require(!s.transfers_succeeded && s.cleanup_complete && submission.canceled[0] && submission.canceled[1], "Partial submission not canceled/drained");
        Fake completion; completion.failed_completion = 0; auto c = sl3::capture_transaction(completion);
        require(!c.transfers_succeeded && c.cleanup_complete && completion.canceled[1] && completion.canceled[3], "Completion failure cleanup");
        Fake hung; hung.stuck = 0; auto h = sl3::capture_transaction(hung);
        require(!h.cleanup_complete && h.retained_slots == std::vector<std::size_t>{0}, "Undrained request not retained");
        require(hung.pending[0], "Stuck transfer ownership lost");
        Fake cancel_error;cancel_error.failed_completion=0;cancel_error.cancel_throws=true;
        auto cancel=sl3::capture_transaction(cancel_error);
        require(!cancel.transfers_succeeded && cancel.cleanup_complete && !cancel_error.pending[3], "Failed cancellation skipped completion drain");
        Fake release_error;release_error.fail_release=1;auto release=sl3::capture_transaction(release_error);
        require(!release.cleanup_complete && release.retained_slots==std::vector<std::size_t>{1}, "Unregister failure incorrectly released ownership");
        require(sl3::capture_transaction(ok, 0).error != "", "Unbounded/empty capture accepted");
        std::cout << "Packet validation and capture lifecycle fault cases passed\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
