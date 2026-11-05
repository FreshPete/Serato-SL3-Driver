using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;

// Filled by the offline capsule preparer, never by command-line interpolation.
const string Python = __PYTHON__;
const string Capsule = __CAPSULE__;
const string CapsuleHash = __CAPSULE_HASH__;
const string Installer = __INSTALLER__;
const string Broker = __BROKER__;
var pins = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
__PINS__
};
bool plan = args.Length == 1 && args[0] == "--plan";
if (!plan && args.Length != 0) return 2;
var leases = new List<FileStream>();
try {
    // Keep exact manifest, interpreter and source bytes stable across UAC and
    // both child invocations. No shell command text or arbitrary actions.
    foreach (var pin in pins) {
        var file = new FileStream(pin.Key, FileMode.Open, FileAccess.Read, FileShare.Read);
        leases.Add(file);
        if (!Convert.ToHexString(SHA256.HashData(file)).Equals(pin.Value, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Reviewed launcher input differs: " + Path.GetFileName(pin.Key));
    }
    int install = Run(Installer, plan ? "plan" : "install", !plan);
    if (plan || install != 0) return install;
    return Run(Broker, "start", false);
} catch (Win32Exception error) {
    Console.Error.WriteLine(error.Message);
    return error.NativeErrorCode == 1223 ? 1223 : 1;
} catch (Exception error) {
    Console.Error.WriteLine(error.Message); return 1;
} finally {
    foreach (var file in leases) file.Dispose();
}

int Run(string script, string action, bool elevate) {
    var start = new ProcessStartInfo {
        FileName = Python, WorkingDirectory = Path.GetDirectoryName(script)!,
        UseShellExecute = elevate, Verb = elevate ? "runas" : "",
        CreateNoWindow = !elevate, WindowStyle = ProcessWindowStyle.Hidden,
        RedirectStandardOutput = !elevate, RedirectStandardError = !elevate
    };
    foreach (var value in new[] { "-I", "-B", script, action, "--capsule", Capsule,
                                 "--expected-capsule-sha256", CapsuleHash }) start.ArgumentList.Add(value);
    using Process child = Process.Start(start) ?? throw new InvalidOperationException("Session helper did not start");
    var output = !elevate ? child.StandardOutput.ReadToEndAsync() : null;
    var error = !elevate ? child.StandardError.ReadToEndAsync() : null;
    // Do not kill an elevated transaction with an unknown commit outcome.
    // Its permit and serialized recovery journal remain the recovery authority.
    child.WaitForExit();
    if (output != null) Console.Write(output.GetAwaiter().GetResult());
    if (error != null) Console.Error.Write(error.GetAwaiter().GetResult());
    return child.ExitCode;
}
