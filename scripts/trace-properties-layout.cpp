// Compile-only Windows x64 SDK checks for the Python ControlTraceW properties ABI.
#include <windows.h>
#include <evntrace.h>
#include <cstddef>

static_assert(sizeof(void*) == 8, "Requires Windows x64");
static_assert(sizeof(GUID) == 16, "GUID extent");
static_assert(sizeof(WNODE_HEADER) == 48, "WNODE header extent");
static_assert(offsetof(WNODE_HEADER, Guid) == 24, "Returned native GUID offset");
static_assert(offsetof(WNODE_HEADER, ClientContext) == 40, "Clock offset");
static_assert(sizeof(EVENT_TRACE_PROPERTIES) == 120, "Properties header extent");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, MaximumFileSize) == 60, "Native limit offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LogFileMode) == 64, "Mode offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, FlushTimer) == 68, "Flush offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, EnableFlags) == 72, "Provider flags offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, EventsLost) == 88, "Lost events offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, BuffersWritten) == 92, "Written buffers offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LogBuffersLost) == 96, "File loss offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, RealTimeBuffersLost) == 100, "Realtime loss offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LogFileNameOffset) == 112, "File name offset");
static_assert(offsetof(EVENT_TRACE_PROPERTIES, LoggerNameOffset) == 116, "Session name offset");
static_assert(EVENT_TRACE_SYSTEM_LOGGER_MODE == 0x02000000, "System logger flag");
static_assert(EVENT_TRACE_CONTROL_QUERY == 0, "Read-only query control code");
