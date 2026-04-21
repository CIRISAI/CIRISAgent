# API Security Configuration Guide

## Network Binding Security

### Default Configuration
By default, the CIRIS API server binds to `127.0.0.1` (localhost only) for security. This prevents unauthorized external access during development and testing.

### Configuration Options

#### Environment Variables
- `CIRIS_API_HOST`: Set the host binding address
  - `127.0.0.1` (default): Localhost only - most secure for development
  - `0.0.0.0`: All network interfaces - use with caution

#### Command Line
```bash
# Secure local development
python main.py --adapter api  # Uses default 127.0.0.1

# External access (use with proper security measures)
python main.py --adapter api --host 0.0.0.0
```

### Security Recommendations

#### Development Environment
- Always use `127.0.0.1` (the default) for local development
- Access the API at `http://localhost:8080`
- No external network access is possible with this configuration

#### Production Deployment
When deploying to production and external access is required:

1. **Use a Reverse Proxy**
   - Deploy behind nginx, Apache, or another reverse proxy
   - Let the proxy handle SSL/TLS termination
   - Keep CIRIS bound to localhost, proxy forwards requests

2. **Firewall Rules**
   - If binding to `0.0.0.0`, always use firewall rules
   - Restrict access to specific IP ranges
   - Block unnecessary ports

3. **Docker Deployments**
   - Docker containers must bind to `0.0.0.0` internally
   - Docker's port mapping provides network isolation
   - Use Docker's network security features

Example nginx configuration:
```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Authentication & Authorization
- Always enable authentication in production (`auth_enabled: true`)
- Use strong passwords for admin accounts
- Implement role-based access control (RBAC)
- Consider implementing API key rotation

#### Service Token Management
Service tokens (`CIRIS_SERVICE_TOKEN`) are used for service-to-service authentication, typically by the CIRIS Manager. These tokens have elevated privileges and should be protected carefully.

**Security Features:**
- **Revocation Support**: Service tokens can be revoked via the API endpoint
- **Audit Logging**: All failed authentication attempts are logged with IP and user agent
- **Constant-Time Comparison**: Tokens are validated using timing-attack-resistant comparison
- **Hash-Based Revocation**: Revoked tokens are stored as SHA-256 hashes for fast lookup

**Revocation Endpoint:**
```bash
# Revoke a service token (requires SYSTEM_ADMIN role)
curl -X POST http://localhost:8080/v1/auth/service-token/revoke \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "service_token_to_revoke",
    "reason": "Security incident - token potentially compromised"
  }'
```

**When to Revoke Service Tokens:**
1. **Security Incident**: Token may have been exposed or compromised
2. **Token Rotation**: Replacing old token with new one
3. **Service Decommissioning**: Service no longer needs access
4. **Suspicious Activity**: Detected unusual authentication patterns

**Best Practices:**
- Rotate service tokens regularly (e.g., every 90 days)
- Store service tokens in secure secret management systems (not in code)
- Monitor failed authentication attempts for anomalies
- Revoke immediately upon suspected compromise
- Use different service tokens for different environments (dev/staging/prod)

### Additional Security Measures
1. Enable rate limiting to prevent abuse
2. Configure CORS appropriately (don't use `*` in production)
3. Monitor access logs for suspicious activity
4. Keep dependencies updated
5. Use HTTPS/TLS for all production deployments

### Common Misconfigurations to Avoid
- ❌ Binding to `0.0.0.0` without firewall rules
- ❌ Disabling authentication in production
- ❌ Using default passwords
- ❌ Allowing unrestricted CORS origins
- ❌ Exposing the API directly without TLS

### Testing Security Configuration
```bash
# Check if API is accessible externally (should fail with 127.0.0.1)
curl http://your-external-ip:8080/v1/system/health

# Check localhost access (should succeed)
curl http://localhost:8080/v1/system/health
```
