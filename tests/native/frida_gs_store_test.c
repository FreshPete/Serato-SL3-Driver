/* Owned-process TLS check. Does not load Frida, Serato or a device driver. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <intrin.h>

typedef uint64_t guint64;
typedef uintptr_t guintptr;
typedef void * gpointer;
typedef DWORD GumTlsKey;

void sl3_reference_gs_store(unsigned long offset, unsigned __int64 value);

/* Same statement as the proposed Clang-only upstream portability change. */
__declspec(noinline) void sl3_candidate_gs_store(GumTlsKey key, gpointer value)
{
  *((guint64 __attribute__((address_space(256))) *) (guintptr)
      (0x1480 + key * sizeof (gpointer))) = (guint64) value;
}

static DWORD keys[64];
static DWORD key_count;
static HANDLE start_event;
static volatile LONG failures;
static volatile LONG comparisons;

static DWORD WINAPI worker(void * parameter)
{
  DWORD identity = (DWORD)(uintptr_t)parameter;
  static const uint64_t patterns[] = {0, 1, UINT64_C(0x123456789abcdef0), UINT64_C(0xfedcba9876543210)};
  if (WaitForSingleObject(start_event, 5000) != WAIT_OBJECT_0)
    return 1;
  for (DWORD round = 0; round < 64; round++)
  {
    for (DWORD index = 0; index < key_count; index++)
    {
      DWORD key = keys[index];
      for (DWORD p = 0; p < sizeof(patterns) / sizeof(patterns[0]); p++)
      {
        uint64_t value = p == 0 ? 0 : patterns[p] ^ ((uint64_t)identity << 32) ^ ((uint64_t)round << 16) ^ key;
        DWORD offset = 0x1480 + key * (DWORD)sizeof(void *);
        SetLastError(0xabc01234);
        sl3_reference_gs_store(offset, value);
        if (GetLastError() != 0xabc01234 || (uintptr_t)TlsGetValue(key) != value)
          InterlockedIncrement(&failures);
        SetLastError(0xabc01234);
        sl3_candidate_gs_store(key, (void *)(uintptr_t)value);
        DWORD candidate_last_error = GetLastError();
        SwitchToThread();
        if (candidate_last_error != 0xabc01234 || (uintptr_t)TlsGetValue(key) != value)
          InterlockedIncrement(&failures);
        if (!TlsSetValue(key, (void *)(uintptr_t)(value ^ UINT64_C(0x55aa55aa55aa55aa))))
          InterlockedIncrement(&failures);
        if (__readgsqword(offset) != (value ^ UINT64_C(0x55aa55aa55aa55aa)))
          InterlockedIncrement(&failures);
        InterlockedAdd(&comparisons, 3);
      }
    }
  }
  for (DWORD index = 0; index < key_count; index++)
    TlsSetValue(keys[index], NULL);
  return 0;
}

int main(void)
{
  HANDLE threads[4] = {0};
  DWORD created = 0;
  int result = 1;
  if (sizeof(void *) != 8)
    return 2;
  for (DWORD index = 0; index < 64; index++)
  {
    DWORD key = TlsAlloc();
    if (key == TLS_OUT_OF_INDEXES)
      break;
    if (key >= 64)
    {
      TlsFree(key);
      break;
    }
    keys[key_count++] = key;
  }
  if (key_count == 0)
    return 3;
  start_event = CreateEventW(NULL, TRUE, FALSE, NULL);
  if (!start_event)
    goto cleanup;
  for (DWORD index = 0; index < key_count; index++)
    if (!TlsSetValue(keys[index], (void *)(uintptr_t)(UINT64_C(0x7fff012345670000) + index)))
      goto cleanup;
  for (; created < 4; created++)
  {
    threads[created] = CreateThread(NULL, 0, worker, (void *)(uintptr_t)(created + 1), 0, NULL);
    if (!threads[created])
      break;
  }
  if (!SetEvent(start_event))
    goto cleanup;
  if (created == 0 || WaitForMultipleObjects(created, threads, TRUE, 15000) != WAIT_OBJECT_0)
    goto cleanup;
  for (DWORD index = 0; index < created; index++)
  {
    DWORD code = 1;
    if (!GetExitCodeThread(threads[index], &code) || code != 0)
      InterlockedIncrement(&failures);
  }
  for (DWORD index = 0; index < key_count; index++)
    if ((uintptr_t)TlsGetValue(keys[index]) != UINT64_C(0x7fff012345670000) + index)
      InterlockedIncrement(&failures);
  result = created == 4 && failures == 0 ? 0 : 1;
cleanup:
  /* All workers are bounded; a failed wait exits only this owned test process. */
  printf("{\"schema\":\"sl3.clang-gs-store-test.v1\",\"threads\":%lu,\"ownedTlsKeys\":%lu,"
         "\"comparisons\":%ld,\"failures\":%ld,\"passed\":%s,\"fridaLoaded\":false,\"deviceOpened\":false}\n",
         created, key_count, comparisons, failures, result == 0 ? "true" : "false");
  for (DWORD index = 0; index < created; index++) CloseHandle(threads[index]);
  if (start_event) CloseHandle(start_event);
  /* On a failed wait, process exit retires workers before their TLS can outlive the process. */
  if (result == 0)
    for (DWORD index = 0; index < key_count; index++) TlsFree(keys[index]);
  return result;
}
