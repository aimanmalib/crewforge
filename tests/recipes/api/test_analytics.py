"""Tests for analytics module."""

from crewforge.recipes.api.analytics import PipelineAnalytics, PipelineMetric


class TestPipelineAnalytics:
    def _metric(self, score=90, tokens=1000, calls=5):
        return PipelineMetric(
            run_id="test",
            description_length=100,
            endpoints_generated=3,
            models_generated=2,
            validation_score=score,
            total_tokens=tokens,
            total_calls=calls,
            duration_seconds=2.5,
            framework="fastapi",
            auth_type="bearer",
        )

    def test_initial(self):
        a = PipelineAnalytics()
        assert a.total_runs == 0
        assert a.average_score() == 0.0

    def test_record(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        assert a.total_runs == 1

    def test_average_score(self):
        a = PipelineAnalytics()
        a.record(self._metric(score=80))
        a.record(self._metric(score=100))
        assert a.average_score() == 90.0

    def test_average_tokens(self):
        a = PipelineAnalytics()
        a.record(self._metric(tokens=1000))
        a.record(self._metric(tokens=2000))
        assert a.average_tokens() == 1500.0

    def test_total_tokens(self):
        a = PipelineAnalytics()
        a.record(self._metric(tokens=100))
        a.record(self._metric(tokens=200))
        assert a.total_tokens_consumed() == 300

    def test_framework_breakdown(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        a.record(
            PipelineMetric(
                run_id="t2",
                description_length=50,
                endpoints_generated=1,
                models_generated=1,
                validation_score=70,
                total_tokens=500,
                total_calls=3,
                duration_seconds=1.0,
                framework="flask",
                auth_type="api_key",
            )
        )
        fb = a.framework_breakdown()
        assert fb["fastapi"] == 1
        assert fb["flask"] == 1

    def test_auth_type_breakdown(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        ab = a.auth_type_breakdown()
        assert ab["bearer"] == 1

    def test_top_runs(self):
        a = PipelineAnalytics()
        for s in [60, 90, 80, 95, 70]:
            a.record(self._metric(score=s))
        top = a.top_runs(3)
        assert top[0].validation_score == 95

    def test_summary(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        s = a.summary()
        assert s["total_runs"] == 1
        assert "average_score" in s

    def test_reset(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        a.reset()
        assert a.total_runs == 0

    def test_average_duration(self):
        a = PipelineAnalytics()
        a.record(self._metric())
        assert a.average_duration() == 2.5

    def test_total_api_calls(self):
        a = PipelineAnalytics()
        a.record(self._metric(calls=5))
        a.record(self._metric(calls=3))
        assert a.total_api_calls() == 8
