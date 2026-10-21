//
//  PythonInit.h
//  CIRIS iOS - Python C API bridge
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Objective-C bridge for Python C API initialization
@interface PythonInit : NSObject

/// Initialize Python interpreter with specified paths
/// @param pythonHome Path to Python stdlib (e.g., .../python)
/// @param appPath Path to app code (e.g., .../app)
/// @param packagesPath Path to third-party packages (e.g., .../app_packages)
/// @param libDynloadPath Path to lib-dynload (native extensions) - use app bundle path on device
/// @return YES if initialization succeeded, NO otherwise
+ (BOOL)initializeWithPythonHome:(NSString *)pythonHome
                         appPath:(NSString *)appPath
                    packagesPath:(NSString *)packagesPath
                   libDynloadPath:(NSString *)libDynloadPath;

/// Run a Python module by name (e.g., "ciris_ios")
/// @param moduleName The module name to run
+ (void)runModule:(NSString *)moduleName;

/// Check if Python is currently initialized
+ (BOOL)isInitialized;

/// Finalize Python interpreter
+ (void)finalize;

@end

NS_ASSUME_NONNULL_END
