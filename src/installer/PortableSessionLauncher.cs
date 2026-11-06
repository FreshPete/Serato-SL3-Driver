using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;

// Release-bound executable, reusable across freshly prepared sessions.
// Environment selects data, never code: all executable/source inputs below
// remain pinned to the release compiled by the offline builder.
const string PythonSha = __PYTHON_SHA__;
const string ApplicationSha = __APPLICATION_SHA__;
var runtimePins = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
__RUNTIME_PINS__
};
var sourcePins = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
__SOURCE_PINS__
};
bool plan = args.Length == 5 && args[0] == "--plan" && args[1] == "--capsule" && args[3] == "--expected-capsule-sha256";
if (!plan && args.Length != 0) return 2;
var leases = new List<FileStream>();
string python = "", capsule = "", capsuleHash = "", installer = "", broker = "";
try {
    capsule = plan ? args[2] : Environment.GetEnvironmentVariable("SL3_SESSION_CAPSULE") ?? "";
    capsuleHash = plan ? args[4] : Environment.GetEnvironmentVariable("SL3_SESSION_CAPSULE_SHA256") ?? "";
    LocalPath(capsule);
    if (Path.GetFileName(capsule) != "session-capsule.json") throw new InvalidOperationException("Expected session capsule filename");
    var manifest = Pin(capsule, capsuleHash);
    if (manifest.Length > 65536) throw new InvalidOperationException("Session capsule exceeds bound");
    using var document = JsonDocument.Parse(manifest);
    var record = document.RootElement;
    if (record.GetProperty("schema").GetString() != "sl3.session-capsule.v1") throw new InvalidOperationException("Unsupported session capsule");
    string root = LocalPath(record.GetProperty("projectRoot").GetString()!);
    if (!String.Equals(record.GetProperty("sessionDirectory").GetString(), Path.GetDirectoryName(capsule), StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Session capsule directory differs");
    foreach (var source in sourcePins) {
        string file = Path.GetFullPath(Path.Combine(root, source.Key));
        if (!file.StartsWith(Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Release source escaped its root");
        Pin(file, source.Value);
    }
    var interpreter = record.GetProperty("python");
    python = LocalPath(interpreter.GetProperty("path").GetString()!);
    if (interpreter.GetProperty("sha256").GetString() != PythonSha) throw new InvalidOperationException("Release interpreter differs");
    Pin(python, PythonSha);
    foreach (var file in runtimePins) {
        string runtimeRoot = Path.GetDirectoryName(python)!;
        string path = Path.GetFullPath(Path.Combine(runtimeRoot, file.Key));
        if (!path.StartsWith(Path.TrimEndingDirectorySeparator(runtimeRoot) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Runtime member escaped its root");
        Pin(path, file.Value);
    }
    var application = record.GetProperty("application");
    if (application.GetProperty("sha256").GetString() != ApplicationSha) throw new InvalidOperationException("Release application differs");
    Pin(LocalPath(application.GetProperty("path").GetString()!), ApplicationSha);
    installer = Path.Combine(root, "scripts", "serato-session-installer.py");
    broker = Path.Combine(root, "scripts", "serato-session-broker.py");
    int installed = Run(installer, plan ? "plan" : "install", !plan);
    if (plan || installed != 0) return installed;
    return Run(broker, "start", false);
} catch (Win32Exception error) {
    Console.Error.WriteLine(error.Message); return error.NativeErrorCode == 1223 ? 1223 : 1;
} catch (Exception error) {
    Console.Error.WriteLine(error.Message); return 1;
} finally {
    foreach (var stream in leases) stream.Dispose();
}

string LocalPath(string value) {
    if (!Path.IsPathFullyQualified(value) || value.StartsWith(@"\\", StringComparison.Ordinal) ||
        Array.IndexOf(value.Replace('/', '\\').Split('\\'), "..") >= 0 || value.IndexOf(':', 2) >= 0)
        throw new InvalidOperationException("Absolute local path without traversal or streams required");
    return value; // Preserve native spelling under packaged Windows callers.
}

FileStream Pin(string path, string expected) {
    if (expected.Length != 64) throw new InvalidOperationException("Expected SHA-256 binding");
    foreach (char character in expected) if (!(character >= '0' && character <= '9') && !(character >= 'a' && character <= 'f'))
        throw new InvalidOperationException("Expected lowercase SHA-256 binding");
    var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
    leases.Add(stream);
    if (!Convert.ToHexString(SHA256.HashData(stream)).Equals(expected, StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Reviewed launcher input differs: " + Path.GetFileName(path));
    stream.Position = 0; return stream;
}

int Run(string script, string action, bool elevate) {
    var start = new ProcessStartInfo {
        FileName = python, WorkingDirectory = Path.GetDirectoryName(script)!,
        UseShellExecute = elevate, Verb = elevate ? "runas" : "", CreateNoWindow = !elevate,
        WindowStyle = ProcessWindowStyle.Hidden, RedirectStandardOutput = !elevate, RedirectStandardError = !elevate
    };
    foreach (var value in new[] { "-I", "-B", script, action, "--capsule", capsule, "--expected-capsule-sha256", capsuleHash })
        start.ArgumentList.Add(value);
    using Process child = Process.Start(start) ?? throw new InvalidOperationException("Session helper did not start");
    var output = !elevate ? child.StandardOutput.ReadToEndAsync() : null;
    var error = !elevate ? child.StandardError.ReadToEndAsync() : null;
    child.WaitForExit(); // Never kill an elevated transaction with unknown commit outcome.
    if (output != null) Console.Write(output.GetAwaiter().GetResult());
    if (error != null) Console.Error.Write(error.GetAwaiter().GetResult());
    return child.ExitCode;
}
