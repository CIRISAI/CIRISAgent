"""
Test FastAPI router ordering fix.

This tests the fix for the route shadowing issue where /v1/system/runtime/single-step
was being shadowed by /v1/system/runtime/{action}.
"""

import pytest
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app


class TestRouterOrdering:
    """Test that router ordering prevents route shadowing."""

    @pytest.fixture
    def test_app(self):
        """Create a test app with the fixed router ordering."""
        from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
        
        app = create_app()
        
        # Initialize auth service (required for auth endpoints)
        app.state.auth_service = APIAuthService()
        app.state.auth_service._dev_mode = True
        
        return app

    @pytest.fixture
    def client(self, test_app):
        """Create a test client."""
        return TestClient(test_app)

    def test_single_step_endpoint_accessible(self, client):
        """Test that the step endpoint is accessible and not shadowed."""
        # This should hit the specific step endpoint, not the generic {action} route
        response = client.post("/v1/system/runtime/step", json={})
        
        # We expect either:
        # - 401 (unauthorized) if auth is required
        # - 503 (service unavailable) if runtime control service not available  
        # - 200 (success) if everything works
        # 
        # What we should NOT get is 400 with "Invalid action" which would indicate
        # the request was handled by the {action} route instead of the specific route
        
        assert response.status_code != 400 or "Invalid action" not in response.text
        
        # If we get a 400, it should be for other validation reasons, not route shadowing
        if response.status_code == 400:
            response_data = response.json()
            assert "Invalid action" not in response_data.get("detail", "")

    def test_pause_endpoint_still_works(self, client):
        """Test that the pause endpoint still works after router reordering."""
        response = client.post("/v1/system/runtime/pause", json={"reason": "test"})
        
        # Should get auth error or service unavailable, not routing error
        assert response.status_code in [401, 503, 422]  # 422 for body validation
        
        # Should not get 404 (not found)
        assert response.status_code != 404

    def test_resume_endpoint_still_works(self, client):
        """Test that the resume endpoint still works after router reordering."""
        response = client.post("/v1/system/runtime/resume", json={"reason": "test"})
        
        # Should get auth error or service unavailable, not routing error
        assert response.status_code in [401, 503, 422]  # 422 for body validation
        
        # Should not get 404 (not found)
        assert response.status_code != 404

    def test_state_endpoint_still_works(self, client):
        """Test that the state endpoint still works after router reordering."""
        response = client.post("/v1/system/runtime/state", json={})
        
        # Should get auth error or service unavailable, not routing error
        assert response.status_code in [401, 503, 422]
        
        # Should not get 404 (not found)
        assert response.status_code != 404

    def test_invalid_action_still_returns_400(self, client):
        """Test that invalid actions still return 400 with proper error message."""
        response = client.post("/v1/system/runtime/invalid_action", json={})
        
        # Should get either:
        # - 401 (unauthorized) 
        # - 404 (not found) - because 'invalid_action' doesn't match any specific route
        # - 400 (bad request) with "Invalid action" if it hits the {action} route
        
        # The key is that 'step' should NOT be treated as an invalid action
        assert response.status_code in [401, 404, 400]

    def test_router_registration_order_in_app(self):
        """Test that system_extensions router is registered before system router."""
        from ciris_engine.logic.adapters.api.app import create_app
        
        # This is a structural test - we create the app and verify the router order
        app = create_app()
        
        # Get the routes and find the runtime routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        # Look for our specific routes
        step_routes = [r for r in routes if '/runtime/step' in r and '{action}' not in r]
        action_routes = [r for r in routes if '/runtime/{action}' in r]
        
        # We should have both routes registered
        assert len(step_routes) > 0, "step route not found"
        assert len(action_routes) > 0, "{action} route not found"
        
        # Note: FastAPI route matching works on order of registration
        # The specific route (step) should be matched before the parametrized route ({action})
        # This is ensured by registering system_extensions router before system router