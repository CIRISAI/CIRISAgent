"""
iOS compatibility shims for cryptography and bcrypt.

BeeWare provides cryptography 3.4.8 which doesn't have the newer
asymmetric.types module. This provides the missing type aliases.

Also provides a pure-Python bcrypt stub using PBKDF2 since native
bcrypt requires Rust compilation not available on iOS.
"""

import sys
from typing import Union

# =============================================================================
# BCRYPT STUB - Must be installed before any bcrypt imports
# =============================================================================

# Import our bcrypt stub which will register itself in sys.modules
import ciris_ios.bcrypt  # noqa: F401 - Installs as 'bcrypt'

# Import our psutil stub which will register itself in sys.modules
import ciris_ios.psutil  # noqa: F401 - Installs as 'psutil'

# Check if we need to provide the types module
try:
    from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes
except ImportError:
    # Create the missing types module for cryptography 3.4.8
    from cryptography.hazmat.primitives.asymmetric import (
        rsa, dsa, ec, ed25519, ed448, x25519, x448, dh
    )

    # Type aliases matching newer cryptography versions
    PrivateKeyTypes = Union[
        rsa.RSAPrivateKey,
        dsa.DSAPrivateKey,
        ec.EllipticCurvePrivateKey,
        ed25519.Ed25519PrivateKey,
        ed448.Ed448PrivateKey,
        x25519.X25519PrivateKey,
        x448.X448PrivateKey,
        dh.DHPrivateKey,
    ]

    PublicKeyTypes = Union[
        rsa.RSAPublicKey,
        dsa.DSAPublicKey,
        ec.EllipticCurvePublicKey,
        ed25519.Ed25519PublicKey,
        ed448.Ed448PublicKey,
        x25519.X25519PublicKey,
        x448.X448PublicKey,
        dh.DHPublicKey,
    ]

    # Inject the types module into cryptography's namespace
    import types
    from cryptography.hazmat.primitives import asymmetric

    types_module = types.ModuleType('cryptography.hazmat.primitives.asymmetric.types')
    types_module.PrivateKeyTypes = PrivateKeyTypes
    types_module.PublicKeyTypes = PublicKeyTypes

    asymmetric.types = types_module
    sys.modules['cryptography.hazmat.primitives.asymmetric.types'] = types_module

    print("[iOS] Installed cryptography.asymmetric.types compatibility shim")
