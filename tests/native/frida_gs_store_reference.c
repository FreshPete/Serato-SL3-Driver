#include <intrin.h>

/* Compiled with MSVC, independently of the Clang candidate. */
__declspec(noinline) void sl3_reference_gs_store(unsigned long offset, unsigned __int64 value)
{
  __writegsqword(offset, value);
}
