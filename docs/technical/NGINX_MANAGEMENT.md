# NGINX Management in CIRIS

## Overview

CIRISManager dynamically generates nginx configurations for all CIRIS agents. This document describes the template-based approach that provides simple, robust routing management.

## Architecture

### Directory Structure
```
/home/ciris/nginx/
├── nginx.conf           # Complete nginx configuration (generated)
├── nginx.conf.new       # Temporary file during updates
└── nginx.conf.backup    # Previous working configuration
```

### Docker Volume Mount
```yaml
ciris-nginx:
  image: nginx:alpine
  volumes:
    - /home/ciris/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  restart: unless-stopped
```

## Configuration Template

CIRISManager generates a complete `nginx.conf` file from discovered agents:

```nginx
events {
    worker_connections 1024;
}

http {
    # Default MIME types and settings
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Performance settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    
    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;
    
    # Size limits
    client_max_body_size 10M;
    
    # === UPSTREAMS ===
    # GUI upstream
    upstream gui {
        server ciris-gui:3000;
    }
    
    # Manager upstream
    upstream manager {
        server host.docker.internal:8888;
    }
    
    # Agent upstreams (dynamically generated)
    upstream agent_datum {
        server 127.0.0.1:8080;
    }
    
    upstream agent_sage {
        server 127.0.0.1:8081;
    }
    
    # === MAIN SERVER ===
    server {
        listen 80;
        server_name _;
        
        # Health check endpoint
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
        
        # GUI routes
        location / {
            proxy_pass http://gui;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Manager routes
        location /manager/v1/ {
            proxy_pass http://manager/manager/v1/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Default API route (Datum)
        location /v1/ {
            proxy_pass http://agent_datum/v1/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }
        
        # Agent-specific OAuth callbacks (dynamically generated)
        location ~ ^/v1/auth/oauth/datum/(.+)/callback$ {
            proxy_pass http://agent_datum/v1/auth/oauth/$1/callback$is_args$args;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Agent-specific API routes (dynamically generated)
        location ~ ^/api/datum/(.*)$ {
            proxy_pass http://agent_datum/$1$is_args$args;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
            
            # WebSocket support
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

## Update Process

1. **Generate New Configuration**
   - CIRISManager discovers all running agents
   - Generates complete nginx.conf from template
   - Writes to `nginx.conf.new`

2. **Validate Configuration**
   ```bash
   docker exec ciris-nginx nginx -t -c /etc/nginx/nginx.conf.new
   ```

3. **Atomic Update**
   ```bash
   # Backup current config
   cp nginx.conf nginx.conf.backup
   
   # Replace with new config
   mv nginx.conf.new nginx.conf
   ```

4. **Reload Nginx**
   ```bash
   docker exec ciris-nginx nginx -s reload
   ```

5. **Rollback on Failure**
   ```bash
   # If reload fails
   mv nginx.conf.backup nginx.conf
   docker exec ciris-nginx nginx -s reload
   ```

## Implementation Details

### NginxManager Class

```python
class NginxManager:
    """Manages nginx configuration using template generation."""
    
    def __init__(self, config_dir: str = "/home/ciris/nginx", 
                 container_name: str = "ciris-nginx"):
        self.config_dir = Path(config_dir)
        self.container_name = container_name
        self.config_path = self.config_dir / "nginx.conf"
        self.new_config_path = self.config_dir / "nginx.conf.new"
        self.backup_path = self.config_dir / "nginx.conf.backup"
        
        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_config(self, agents: List[AgentInfo]) -> str:
        """Generate complete nginx configuration from template."""
        config = self._generate_base_config()
        config += self._generate_upstreams(agents)
        config += self._generate_server_block(agents)
        return config
        
    def update_config(self, agents: List[AgentInfo]) -> bool:
        """Update nginx configuration atomically."""
        try:
            # 1. Generate new config
            new_config = self.generate_config(agents)
            
            # 2. Write to temporary file
            self.new_config_path.write_text(new_config)
            
            # 3. Validate configuration
            if not self._validate_config():
                return False
                
            # 4. Backup current config
            if self.config_path.exists():
                shutil.copy2(self.config_path, self.backup_path)
                
            # 5. Atomic replace
            os.rename(self.new_config_path, self.config_path)
            
            # 6. Reload nginx
            return self._reload_nginx()
            
        except Exception as e:
            logger.error(f"Failed to update nginx config: {e}")
            self._rollback()
            return False
    
    def _validate_config(self) -> bool:
        """Validate nginx configuration."""
        result = subprocess.run([
            'docker', 'exec', self.container_name,
            'nginx', '-t', '-c', f'/etc/nginx/nginx.conf.new'
        ], capture_output=True)
        return result.returncode == 0
        
    def _reload_nginx(self) -> bool:
        """Reload nginx configuration."""
        result = subprocess.run([
            'docker', 'exec', self.container_name,
            'nginx', '-s', 'reload'
        ], capture_output=True)
        return result.returncode == 0
```

### Route Priority

Routes are ordered by specificity to prevent conflicts:

1. Health check endpoints
2. Static assets and GUI
3. Manager API routes
4. OAuth callbacks (most specific)
5. Agent-specific API routes
6. Default API route (catch-all)

### Production Considerations

1. **SSL/TLS**: Production adds SSL configuration
2. **Rate Limiting**: Can be added per route
3. **CORS Headers**: Added as needed
4. **Logging**: Separate access logs per agent
5. **Monitoring**: Health endpoints for each service

## Benefits

1. **Simplicity**: One file, easy to understand
2. **Atomicity**: All-or-nothing updates
3. **Debuggability**: Can inspect complete config
4. **Performance**: No include processing overhead
5. **Reliability**: Config validation before deployment

## Initial Setup

Run the setup script to prepare nginx management:

```bash
./deployment/setup-nginx-management.sh
```

This script will:
1. Create the nginx config directory (`/home/ciris/nginx`)
2. Set proper ownership for CIRISManager
3. Generate initial nginx configuration if possible
4. Verify nginx container configuration
5. Provide next steps for docker-compose setup

## Migration from Static Config

1. Stop using docker build for nginx configs
2. Mount config directory as volume
3. Let CIRISManager generate initial config
4. Remove all hardcoded agent routes
5. Test with single agent, then scale up

## Troubleshooting

### Config not updating
```bash
# Check file permissions
ls -la /home/ciris/nginx/

# Check nginx process can read config
docker exec ciris-nginx cat /etc/nginx/nginx.conf

# Check for syntax errors
docker exec ciris-nginx nginx -t
```

### Routes not working
```bash
# Verify config has the route
grep "location.*api/myagent" /home/ciris/nginx/nginx.conf

# Check upstream exists
grep "upstream agent_myagent" /home/ciris/nginx/nginx.conf

# Test directly
curl -v http://localhost/api/myagent/v1/system/health
```

### Rollback procedure
```bash
# Restore previous config
cp /home/ciris/nginx/nginx.conf.backup /home/ciris/nginx/nginx.conf

# Reload nginx
docker exec ciris-nginx nginx -s reload

# Verify it's working
curl http://localhost/health
```

## Future Enhancements

1. **Metrics**: Export nginx metrics to Prometheus
2. **Blue-Green**: Support staged deployments
3. **Circuit Breaking**: Add failure detection
4. **Request Tracing**: Add correlation IDs
5. **A/B Testing**: Route percentages of traffic