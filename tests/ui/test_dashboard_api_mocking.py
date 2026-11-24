"""
test_dashboard_api_mocking.py

Tests how a dashboard UI reacts to different backend API responses,
using Playwright's page.route() to intercept and mock API calls
in the browser — no real backend needed.

Three scenarios tested:
  1. Data accuracy  — API returns metrics; UI must render the exact values
  2. Empty state    — API returns no records; UI must show a clean empty message
  3. 500 error      — API fails; UI must show a graceful error, not crash
"""

import json
import pytest
from playwright.sync_api import Page

# ---------------------------------------------------------------------------
# A minimal dashboard page that fetches campaign metrics from an API.
# In a real app this would be your deployed URL — here we use a local mock
# URL so page.route() can intercept it without any real server running.
# ---------------------------------------------------------------------------
MOCK_API_URL = "http://localhost:8888/api/campaigns"

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<body>
  <div id="metrics">Loading...</div>
  <div id="error" style="display:none">Failed to load dashboard data</div>
  <script>
    fetch("http://localhost:8888/api/campaigns")
      .then(function(resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        return resp.json();
      })
      .then(function(data) {
        var el = document.getElementById("metrics");
        if (data.length === 0) {
          el.textContent = "No data available";
        } else {
          el.textContent = "Clicks: " + data[0].clicks + " | Impressions: " + data[0].impressions;
        }
      })
      .catch(function() {
        document.getElementById("metrics").textContent = "";
        document.getElementById("error").style.display = "block";
      });
  </script>
</body>
</html>
"""


class TestDashboardAPIMocking:
    """
    Validates dashboard UI behaviour across three backend API states.

    page.route() intercepts the fetch() call inside the browser before
    it reaches any real server and returns whatever response we tell it to.
    This lets us test exact edge cases reliably and without flakiness.
    """

    def test_ui_renders_correct_metrics_from_api_payload(self, page: Page):
        """
        Data Accuracy:
        Mock API returns specific click and impression values.
        Assert the UI displays those exact numbers — not stale or hardcoded values.

        Why this matters for dashboards: data pipelines can silently drop or
        transform fields; this test catches a UI that shows the wrong numbers
        even when the API responds successfully.
        """
        # Step 1: Tell Playwright to intercept any request to MOCK_API_URL
        # and return our controlled JSON payload instead of hitting a real server.
        page.route(
            MOCK_API_URL,
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps([{"clicks": 1500, "impressions": 42000}])
            )
        )

        # Step 2: Load the dashboard. The fetch() inside the HTML fires on load
        # and is immediately intercepted by the route we set up above.
        page.set_content(DASHBOARD_HTML)

        # Step 3: Wait until the UI has finished rendering (stops showing "Loading...")
        page.wait_for_function(
            "document.getElementById('metrics').textContent !== 'Loading...'"
        )

        # Step 4: Assert the exact values from the mock payload appear in the UI
        metrics_text = page.locator("#metrics").text_content()
        assert "1500" in metrics_text, f"Expected clicks '1500' in: {metrics_text}"
        assert "42000" in metrics_text, f"Expected impressions '42000' in: {metrics_text}"

    def test_ui_shows_empty_state_when_api_returns_no_records(self, page: Page):
        """
        Empty State:
        Mock API returns an empty list [].
        Assert the UI shows 'No data available' — not a blank, broken, or crashed screen.

        Why this matters: empty API responses are common at dashboard launch or after
        filters; a UI that crashes or shows nothing is a poor user experience.
        """
        # Return a valid 200 response but with an empty array
        page.route(
            MOCK_API_URL,
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body="[]"
            )
        )

        page.set_content(DASHBOARD_HTML)
        page.wait_for_function(
            "document.getElementById('metrics').textContent !== 'Loading...'"
        )

        assert page.locator("#metrics").text_content() == "No data available"

    def test_ui_handles_500_server_error_gracefully(self, page: Page):
        """
        Error Resilience:
        Mock API returns HTTP 500 Internal Server Error.
        Assert the UI shows a user-friendly error message — not a blank screen
        or an unhandled exception visible to the user.

        Why this matters: backend failures are inevitable; a well-tested dashboard
        degrades gracefully instead of silently breaking or showing raw error codes.
        """
        # Return a 500 — simulates a backend crash or deployment failure
        page.route(
            MOCK_API_URL,
            lambda route: route.fulfill(
                status=500,
                body="Internal Server Error"
            )
        )

        page.set_content(DASHBOARD_HTML)

        # Wait for the error div to become visible (the catch() block in the HTML fires it)
        page.wait_for_function(
            "document.getElementById('error').style.display !== 'none'"
        )

        error_el = page.locator("#error")
        assert error_el.is_visible(), "Error message should be visible on 500 response"
        assert "Failed to load dashboard data" in error_el.text_content()
