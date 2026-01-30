//
//  PythonInit.m
//  CIRIS iOS - Python C API bridge implementation
//

#import "PythonInit.h"
#include <Python/Python.h>

@implementation PythonInit

static BOOL _isInitialized = NO;

+ (BOOL)initializeWithPythonHome:(NSString *)pythonHome
                         appPath:(NSString *)appPath
                    packagesPath:(NSString *)packagesPath {

    if (_isInitialized) {
        NSLog(@"[PythonInit] Already initialized");
        return YES;
    }

    PyStatus status;
    PyPreConfig preconfig;
    PyConfig config;
    NSString *pythonTag = @"3.10";
    NSString *path;
    wchar_t *wtmp_str;

    NSLog(@"[PythonInit] Configuring isolated Python...");
    PyPreConfig_InitIsolatedConfig(&preconfig);
    PyConfig_InitIsolatedConfig(&config);

    // Configure the Python interpreter
    preconfig.utf8_mode = 1;
    preconfig.configure_locale = 1;
    config.buffered_stdio = 0;
    config.write_bytecode = 0;
    config.module_search_paths_set = 1;

    NSLog(@"[PythonInit] Pre-initializing Python runtime...");
    status = Py_PreInitialize(&preconfig);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to pre-initialize Python: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // Set Python home
    NSLog(@"[PythonInit] PythonHome: %@", pythonHome);
    wtmp_str = Py_DecodeLocale([pythonHome UTF8String], NULL);
    status = PyConfig_SetString(&config, &config.home, wtmp_str);
    PyMem_RawFree(wtmp_str);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to set PYTHONHOME: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // Read site config
    status = PyConfig_Read(&config);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to read site config: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // Set module search paths
    NSLog(@"[PythonInit] PYTHONPATH:");

    // stdlib
    path = [NSString stringWithFormat:@"%@/lib/python%@", pythonHome, pythonTag];
    NSLog(@"[PythonInit] - %@", path);
    wtmp_str = Py_DecodeLocale([path UTF8String], NULL);
    status = PyWideStringList_Append(&config.module_search_paths, wtmp_str);
    PyMem_RawFree(wtmp_str);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to set stdlib path: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // lib-dynload
    path = [NSString stringWithFormat:@"%@/lib/python%@/lib-dynload", pythonHome, pythonTag];
    NSLog(@"[PythonInit] - %@", path);
    wtmp_str = Py_DecodeLocale([path UTF8String], NULL);
    status = PyWideStringList_Append(&config.module_search_paths, wtmp_str);
    PyMem_RawFree(wtmp_str);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to set lib-dynload path: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // app path
    NSLog(@"[PythonInit] - %@", appPath);
    wtmp_str = Py_DecodeLocale([appPath UTF8String], NULL);
    status = PyWideStringList_Append(&config.module_search_paths, wtmp_str);
    PyMem_RawFree(wtmp_str);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to set app path: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    // Initialize Python
    NSLog(@"[PythonInit] Initializing Python runtime...");
    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) {
        NSLog(@"[PythonInit] ERROR: Unable to initialize Python: %s", status.err_msg);
        PyConfig_Clear(&config);
        return NO;
    }

    PyConfig_Clear(&config);

    // Add app_packages as site directory
    NSLog(@"[PythonInit] Adding app_packages as site directory: %@", packagesPath);

    PyObject *site_module = PyImport_ImportModule("site");
    if (site_module == NULL) {
        NSLog(@"[PythonInit] ERROR: Could not import site module");
        PyErr_Print();
        return NO;
    }

    PyObject *addsitedir = PyObject_GetAttrString(site_module, "addsitedir");
    if (addsitedir == NULL || !PyCallable_Check(addsitedir)) {
        NSLog(@"[PythonInit] ERROR: Could not access site.addsitedir");
        Py_XDECREF(addsitedir);
        Py_DECREF(site_module);
        return NO;
    }

    PyObject *packages_path_obj = PyUnicode_FromString([packagesPath UTF8String]);
    PyObject *args = Py_BuildValue("(O)", packages_path_obj);
    PyObject *result = PyObject_CallObject(addsitedir, args);

    Py_XDECREF(result);
    Py_DECREF(args);
    Py_DECREF(packages_path_obj);
    Py_DECREF(addsitedir);
    Py_DECREF(site_module);

    if (result == NULL) {
        NSLog(@"[PythonInit] ERROR: Failed to add app_packages to site");
        PyErr_Print();
        return NO;
    }

    _isInitialized = YES;
    NSLog(@"[PythonInit] Python initialization complete!");
    return YES;
}

+ (void)runModule:(NSString *)moduleName {
    if (!_isInitialized) {
        NSLog(@"[PythonInit] ERROR: Python not initialized");
        return;
    }

    NSLog(@"[PythonInit] Running module: %@", moduleName);

    PyObject *runpy_module = PyImport_ImportModule("runpy");
    if (runpy_module == NULL) {
        NSLog(@"[PythonInit] ERROR: Could not import runpy module");
        PyErr_Print();
        return;
    }

    PyObject *run_module = PyObject_GetAttrString(runpy_module, "_run_module_as_main");
    if (run_module == NULL) {
        NSLog(@"[PythonInit] ERROR: Could not access runpy._run_module_as_main");
        Py_DECREF(runpy_module);
        PyErr_Print();
        return;
    }

    PyObject *module_name_obj = PyUnicode_FromString([moduleName UTF8String]);
    PyObject *args = Py_BuildValue("(Oi)", module_name_obj, 0);

    NSLog(@"[PythonInit] ---------------------------------------------------------------------------");

    PyObject *result = PyObject_Call(run_module, args, NULL);

    if (result == NULL) {
        NSLog(@"[PythonInit] ERROR: Module execution failed");
        PyErr_Print();
    }

    Py_XDECREF(result);
    Py_DECREF(args);
    Py_DECREF(module_name_obj);
    Py_DECREF(run_module);
    Py_DECREF(runpy_module);
}

+ (BOOL)isInitialized {
    return _isInitialized;
}

+ (void)finalize {
    if (_isInitialized) {
        NSLog(@"[PythonInit] Finalizing Python...");
        Py_Finalize();
        _isInitialized = NO;
    }
}

@end
