// Original capture-only diagnostic. No driver installation, security-policy
// edits, firmware, rate setters, routing commands or audio OUT submissions.
#include <windows.h>
#include <setupapi.h>
#include <winusb.h>
#include <usb.h>
#include "core/capture.hpp"
#include "core/playback.hpp"
#include "windows/sl3_fixture.hpp"
#include "windows/diagnostic.hpp"
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cwctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {
constexpr GUID project_guid{0x45dfc124, 0x470c, 0x4c58, {0xba,0x2b,0xbf,0xf7,0x61,0x4a,0x64,0xbc}};
constexpr unsigned requests = 4, packets_per_request = 64, bytes_per_request = packets_per_request * 126;
using namespace sl3::diagnostic;

struct Device {
    HANDLE file = INVALID_HANDLE_VALUE;
    std::array<WINUSB_INTERFACE_HANDLE,4> by_number{};
    std::vector<WINUSB_INTERFACE_HANDLE> owned;
    std::vector<unsigned> attempted;
    bool restored = true;
    ~Device() {
        restore();
        for (auto i = owned.rbegin(); i != owned.rend(); ++i) WinUsb_Free(*i);
        if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    }
    void open() {
        HDEVINFO info = SetupDiGetClassDevsW(&project_guid, nullptr, nullptr, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
        if (info == INVALID_HANDLE_VALUE) failed("SetupDiGetClassDevs");
        std::vector<std::wstring> paths;
        try {
            for (DWORD i = 0;; ++i) {
                SP_DEVICE_INTERFACE_DATA item{}; item.cbSize = sizeof(item);
                if (!SetupDiEnumDeviceInterfaces(info, nullptr, &project_guid, i, &item)) {
                    if (GetLastError() == ERROR_NO_MORE_ITEMS) break;
                    failed("SetupDiEnumDeviceInterfaces");
                }
                DWORD length = 0;
                SetupDiGetDeviceInterfaceDetailW(info, &item, nullptr, 0, &length, nullptr);
                if (GetLastError() != ERROR_INSUFFICIENT_BUFFER) failed("Interface detail size");
                std::vector<unsigned char> storage(length);
                auto* detail = reinterpret_cast<SP_DEVICE_INTERFACE_DETAIL_DATA_W*>(storage.data());
                detail->cbSize = sizeof(*detail);
                if (!SetupDiGetDeviceInterfaceDetailW(info, &item, detail, length, nullptr, nullptr)) failed("Interface detail");
                std::wstring path(detail->DevicePath), lower = path;
                std::transform(lower.begin(), lower.end(), lower.begin(), [](wchar_t c) { return wchar_t(towlower(c)); });
                if (lower.find(L"usb#vid_1cc5&pid_0001#") != std::wstring::npos) paths.push_back(path);
            }
        } catch (...) { SetupDiDestroyDeviceInfoList(info); throw; }
        SetupDiDestroyDeviceInfoList(info);
        if (paths.size() != 1) throw std::runtime_error("Exactly one project SL3 interface must already be bound to WinUSB");
        file = CreateFileW(paths[0].c_str(), GENERIC_READ|GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
        if (file == INVALID_HANDLE_VALUE) failed("Exclusive SL3 open");
        owned.reserve(4);
        WINUSB_INTERFACE_HANDLE primary{};
        if (!WinUsb_Initialize(file, &primary)) failed("WinUsb_Initialize");
        owned.push_back(primary);
        for (UCHAR i = 0; i < 3; ++i) {
            WINUSB_INTERFACE_HANDLE associated{};
            if (!WinUsb_GetAssociatedInterface(primary, i, &associated)) failed("Associated interface");
            owned.push_back(associated);
        }
        USB_DEVICE_DESCRIPTOR descriptor{}; ULONG length = 0;
        if (!WinUsb_GetDescriptor(primary, USB_DEVICE_DESCRIPTOR_TYPE, 0, 0, reinterpret_cast<PUCHAR>(&descriptor), sizeof(descriptor), &length)) failed("Device descriptor");
        if (length != sizeof(descriptor) || descriptor.idVendor != 0x1cc5 || descriptor.idProduct != 1 || descriptor.bNumConfigurations != 1) throw std::runtime_error("Device identity differs from fixture");
        std::array<UCHAR,235> config{};
        if (!WinUsb_GetDescriptor(primary, USB_CONFIGURATION_DESCRIPTOR_TYPE, 0, 0, config.data(), ULONG(config.size()), &length)) failed("Configuration descriptor");
        if (length != config.size() || config != sl3::configuration_fixture) throw std::runtime_error("Configuration differs from verified fixture");
        UCHAR speed=0;length=sizeof(speed);
        if (!WinUsb_QueryDeviceInformation(primary,DEVICE_SPEED,&length,&speed)) failed("USB speed query");
        if (length!=sizeof(speed) || speed!=3) throw std::runtime_error("High-speed operation is required for the capture schedule");
        for (auto handle : owned) {
            USB_INTERFACE_DESCRIPTOR d{}; UCHAR active = 255;
            if (!WinUsb_QueryInterfaceSettings(handle, 0, &d) || !WinUsb_GetCurrentAlternateSetting(handle, &active)) failed("Interface identity");
            if (d.bInterfaceNumber > 3 || by_number[d.bInterfaceNumber] || active != 0) throw std::runtime_error("Expected four unique interfaces at alternate zero");
            by_number[d.bInterfaceNumber] = handle;
        }
        verify_pipe(1,1,0,0x06,UsbdPipeTypeIsochronous,126);
        verify_pipe(2,1,0,0x82,UsbdPipeTypeIsochronous,126);
        verify_pipe(3,0,0,0x81,UsbdPipeTypeInterrupt,64);
        verify_pipe(3,0,1,0x01,UsbdPipeTypeInterrupt,64);
    }
    void verify_pipe(unsigned iface, UCHAR alternate, UCHAR index, UCHAR id, USBD_PIPE_TYPE type, ULONG maximum) {
        WINUSB_PIPE_INFORMATION_EX pipe{};
        if (!WinUsb_QueryPipeEx(by_number[iface], alternate, index, &pipe)) failed("Pipe query");
        if (pipe.PipeId != id || pipe.PipeType != type || pipe.MaximumPacketSize != maximum || pipe.MaximumBytesPerInterval != maximum || pipe.Interval != 1) throw std::runtime_error("Pipe fixture mismatch");
    }
    unsigned read_rate() {
        auto control = by_number[3];
        std::vector<std::pair<UCHAR,ULONG>> old;
        auto restore_timeouts = [&]() {
            bool ok = true;
            for (auto p : old) { auto value = p.second; if (!WinUsb_SetPipePolicy(control,p.first,PIPE_TRANSFER_TIMEOUT,sizeof(value),&value)) ok = false; }
            return ok;
        };
        unsigned rate = 0;
        try {
            for (auto p : {std::pair<UCHAR,ULONG>{UCHAR(0x81),ULONG(300)}, std::pair<UCHAR,ULONG>{UCHAR(0x01),ULONG(100)}}) {
                ULONG value{}, size = sizeof(value);
                if (!WinUsb_GetPipePolicy(control,p.first,PIPE_TRANSFER_TIMEOUT,&size,&value)) failed("Get pipe timeout");
                old.emplace_back(p.first,value); value=p.second;
                if (!WinUsb_SetPipePolicy(control,p.first,PIPE_TRANSFER_TIMEOUT,sizeof(value),&value)) failed("Set pipe timeout");
            }
            std::array<UCHAR,64> data{}; data[0]=0x30; data[1]=0x1c; data[2]=0xc5; data[4]=1; ULONG length=0;
            if (!WinUsb_WritePipe(control,0x01,data.data(),ULONG(data.size()),&length,nullptr)) failed("Rate getter write");
            if (length != 64) throw std::runtime_error("Short rate-getter write");
            for (unsigned attempt=0; attempt<4; ++attempt) {
                data.fill(0);
                if (!WinUsb_ReadPipe(control,0x81,data.data(),ULONG(data.size()),&length,nullptr)) failed("Rate getter read");
                if (length != 64) throw std::runtime_error("Incomplete status frame");
                if (data[0]==0x30 && data[1]==0x1c && data[2]==0xc5 && data[3]==0 && data[4]==1) { rate=(unsigned(data[5])<<8)|data[6]; break; }
                const auto command=data[0];
                const UCHAR tag=command==0x34?1:command==0x38?2:command==0x39?3:0;
                if (!tag || data[1] || data[2] || data[3] || data[4]!=tag) throw std::runtime_error("Unrecognized status while awaiting rate");
            }
        } catch (...) { restore_timeouts(); throw; }
        if (!restore_timeouts()) throw std::runtime_error("Could not restore pipe timeouts");
        if (rate!=44100 && rate!=48000) throw std::runtime_error("No recognized current rate; no audio submitted");
        return rate;
    }
    void activate() {
        restored=false;
        for (unsigned i : {1u,2u}) {
            attempted.push_back(i);
            if (!WinUsb_SetCurrentAlternateSetting(by_number[i],1)) failed("Audio alternate activation");
            UCHAR active=255;
            if (!WinUsb_GetCurrentAlternateSetting(by_number[i],&active) || active!=1) throw std::runtime_error("Audio alternate readback failed");
        }
    }
    bool restore() noexcept {
        bool ok=true;
        for (auto i=attempted.rbegin();i!=attempted.rend();++i) {
            UCHAR active=255;
            if (!WinUsb_SetCurrentAlternateSetting(by_number[*i],0) || !WinUsb_GetCurrentAlternateSetting(by_number[*i],&active) || active!=0) ok=false;
        }
        attempted.clear(); restored=ok; return ok;
    }
};

struct NativeCapture final : sl3::CaptureBackend {
    struct Slot {
        std::vector<UCHAR> buffer;
        std::vector<USBD_ISO_PACKET_DESCRIPTOR> packets;
        OVERLAPPED overlapped{};
        WINUSB_ISOCH_BUFFER_HANDLE registered{};
        bool pending=false;
        DWORD completion_error=0;
        std::string submitted_utc,completed_utc;
    };
    Device& device;
    std::array<Slot,requests> slots;
    std::size_t submitted=0;
    std::size_t completed=0;
    explicit NativeCapture(Device& d):device(d){}
    ~NativeCapture() {
        for (const auto& s:slots) if (s.pending || s.registered) fail_stop();
    }
    void prepare(std::size_t i) override {
        auto& s=slots.at(i); s.buffer.resize(bytes_per_request); s.packets.resize(packets_per_request);
        s.overlapped.hEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        if (!s.overlapped.hEvent) failed("Create completion event");
        if (!WinUsb_RegisterIsochBuffer(device.by_number[2],0x82,s.buffer.data(),ULONG(s.buffer.size()),&s.registered)) {
            const auto error=GetLastError(); CloseHandle(s.overlapped.hEvent);s.overlapped.hEvent=nullptr;SetLastError(error);failed("Register IN buffer");
        }
    }
    void submit(std::size_t i,bool next) override {
        auto& s=slots.at(i);
        s.submitted_utc=utc_now();
        const auto accepted=WinUsb_ReadIsochPipeAsap(s.registered,0,ULONG(s.buffer.size()),next?TRUE:FALSE,ULONG(s.packets.size()),s.packets.data(),&s.overlapped);
        if (!accepted && GetLastError()!=ERROR_IO_PENDING) failed("Submit isochronous IN");
        s.pending=true;
        ++submitted;
    }
    sl3::Completion wait(std::size_t i,std::uint32_t timeout) override {
        auto& s=slots.at(i);
        const auto status=WaitForSingleObject(s.overlapped.hEvent,timeout);
        if (status==WAIT_TIMEOUT) return sl3::Completion::pending;
        if (status!=WAIT_OBJECT_0) failed("Wait for capture completion");
        ULONG transferred=0;
        // This API requires the primary handle from WinUsb_Initialize, even
        // when the request targets an associated interface.
        if (!WinUsb_GetOverlappedResult(device.owned.front(),&s.overlapped,&transferred,FALSE)) {
            s.completion_error=GetLastError();
            if (s.completion_error==ERROR_IO_INCOMPLETE) return sl3::Completion::pending;
            s.pending=false;s.completed_utc=utc_now();++completed;return sl3::Completion::failure;
        }
        s.pending=false;s.completed_utc=utc_now();++completed;return sl3::Completion::success;
    }
    void cancel(std::size_t i) override {
        auto& s=slots.at(i);
        if (!CancelIoEx(device.file,&s.overlapped) && GetLastError()!=ERROR_NOT_FOUND) failed("Cancel capture request");
    }
    void release(std::size_t i) override {
        auto& s=slots.at(i);
        if (s.pending) throw std::runtime_error("Attempted to release pending I/O");
        if (s.registered && !WinUsb_UnregisterIsochBuffer(s.registered)) failed("Unregister IN buffer");
        s.registered=nullptr;
        if (s.overlapped.hEvent) CloseHandle(s.overlapped.hEvent);
        s.overlapped.hEvent=nullptr;
    }
    std::uint64_t now_ms() const override { return GetTickCount64(); }
};
}

int wmain(int argc,wchar_t** argv) {
    bool capture=false,plan=false;std::filesystem::path output;
    for (int i=1;i<argc;++i) {
        const std::wstring arg=argv[i];
        if (arg==L"--capture") capture=true;
        else if (arg==L"--output" && i+1<argc) output=argv[++i];
        else if (arg==L"--plan") plan=true;
        else { std::cerr<<"Usage: sl3_capture [--plan | --capture --output NEW_DIRECTORY]\n";return 2; }
    }
    if(capture && plan){std::cerr<<"Plan and capture modes are mutually exclusive\n";return 2;}
    if (!capture) { std::cout<<"{\"plan_only\":true,\"scheduled_ms\":32,\"audio_direction\":\"IN only\",\"rate_query\":\"0x30 getter only\",\"driver_changes\":false}\n";return 0; }
    if (output.empty() || std::filesystem::exists(output)) { std::cerr<<"A new output directory is required\n";return 2; }
    if (!output.parent_path().empty()) std::filesystem::create_directories(output.parent_path());
    if (!std::filesystem::create_directory(output)) { std::cerr<<"Output directory appeared concurrently; refusing overwrite\n";return 2; }
    std::ofstream report(output/L"capture.json");
    if (!report) { std::cerr<<"Could not create capture record; no device opened\n";return 2; }
    report<<"{\"phase\":\"before device open\"}\n"<<std::flush;
    Watchdog watchdog;
    const auto started_utc=utc_now();
    Device device;unsigned rate=0;std::string error;bool captured=false,restored=true,transfers=false;std::size_t frames=0,zero_packets=0,submitted=0,completed=0;
    bool playback_layout_validated=false,winusb_maximum_packet_shape=false;
    std::vector<sl3::Frame> decoded_frames;
    std::vector<std::uint32_t> packet_lengths;
    std::ostringstream packet_json;packet_json<<'[';bool first=true;
    try {
        device.open();rate=device.read_rate();device.activate();
        NativeCapture backend(device);
        const auto result=sl3::capture_transaction(backend);
        submitted=backend.submitted;
        completed=backend.completed;transfers=result.transfers_succeeded;
        if (!result.cleanup_complete) {
            report.seekp(0);report<<"{\"cleanup_complete\":false,\"process_teardown_required\":true,\"error\":"<<quote(result.error)<<"}\n"<<std::flush;
            fail_stop();
        }
        // All requests are terminal before any packet memory is inspected.
        std::ofstream raw(output/L"capture.pcm",std::ios::binary);
        for (std::size_t i=0;i<backend.slots.size();++i) {
            const auto& slot=backend.slots[i];
            std::ofstream registered(output/(L"registered-"+std::to_wstring(i)+L".bin"),std::ios::binary);
            registered.write(reinterpret_cast<const char*>(slot.buffer.data()),std::streamsize(slot.buffer.size()));
            for (std::size_t j=0;j<slot.packets.size();++j) {
                const auto& p=slot.packets[j];
                if (!first) packet_json<<',';first=false;
                packet_json<<"{\"request\":"<<i<<",\"submitted_utc\":"<<quote(slot.submitted_utc)<<",\"completed_utc\":"<<quote(slot.completed_utc)<<",\"completion_win32_error\":"<<slot.completion_error<<",\"packet\":"<<j<<",\"offset\":"<<p.Offset<<",\"length\":"<<p.Length<<",\"status\":"<<static_cast<std::uint32_t>(p.Status)<<'}';
            }
            // Preserve all request metadata before decoding any packet.
        }
        if (result.transfers_succeeded) for (const auto& slot:backend.slots) {
                std::vector<sl3::Packet> packets;
                for (const auto& p:slot.packets) packets.push_back({p.Offset,p.Length,static_cast<std::uint32_t>(p.Status)});
                const auto decoded=sl3::decode_capture(slot.buffer,packets);
                frames+=decoded.frames.size();zero_packets+=decoded.zero_packets;
                decoded_frames.insert(decoded_frames.end(),decoded.frames.begin(),decoded.frames.end());
                for(const auto& p:packets) packet_lengths.push_back(p.length);
                if (!decoded.packed_pcm.empty()) raw.write(reinterpret_cast<const char*>(decoded.packed_pcm.data()),std::streamsize(decoded.packed_pcm.size()));
        }
        if (!raw) throw std::runtime_error("Could not save PCM evidence");
        if (!result.transfers_succeeded) throw std::runtime_error(result.error);
        if (zero_packets || !frames) throw std::runtime_error("Empty packets observed; retain capture but do not claim valid audio");
        // Offline repacking checks the original driver's mirrored-length
        // contract. This neither submits output nor selects a playback backend.
        const auto layout=sl3::make_playback_layout(packet_lengths,decoded_frames);
        playback_layout_validated=true;
        winusb_maximum_packet_shape=layout.winusb_maximum_packet_shape;
        captured=true;
    } catch (const std::exception& e) { error=e.what(); }
    restored=device.restore();packet_json<<']';
    report.close();report.open(output/L"capture.json",std::ios::trunc);
    report<<"{\"started_utc\":"<<quote(started_utc)<<",\"completed_utc\":"<<quote(utc_now())<<",\"capture_succeeded\":"<<(captured?"true":"false")<<",\"transfers_succeeded\":"<<(transfers?"true":"false")<<",\"buffer_cleanup_complete\":true,\"alternates_restored\":"<<(restored?"true":"false")
          <<",\"reported_rate_hz\":"<<rate<<",\"planned_intervals\":256,\"planned_ms\":32,\"submitted_requests\":"<<submitted<<",\"completed_requests\":"<<completed<<",\"frames\":"<<frames
          <<",\"zero_packets\":"<<zero_packets<<",\"offline_playback_layout_validated\":"<<(playback_layout_validated?"true":"false")
          <<",\"winusb_maximum_packet_shape\":"<<(winusb_maximum_packet_shape?"true":"false")<<",\"audio_output_submissions\":0"
          <<",\"sample_format\":\"six logical channels, packed signed 24-bit little-endian\",\"error\":"<<quote(error)<<",\"packets\":"<<packet_json.str()<<"}\n";
    return captured && restored && report?0:1;
}
