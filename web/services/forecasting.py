import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("[FORECASTING]")

class HealthForecaster:
    """
    Service to predict future resource usage based on historical trends.
    Uses simple linear regression for forecasting.
    """
    _cache = {}
    _cache_ttl_sec = 30
    
    @staticmethod
    def predict_threshold_arrival(timestamps, values, threshold=95.0):
        """
        Predict when a value will hit the specified threshold.
        Returns: datetime or None if prediction is impossible or stable.
        """
        if len(values) < 5:
            return None
            
        # Convert timestamps to seconds from the first timestamp
        start_time = timestamps[0]
        x = np.array([(ts - start_time).total_seconds() for ts in timestamps]).reshape(-1, 1)
        y = np.array(values)
        
        # Linear Regression: y = mx + c
        # We solve for x when y = threshold -> x = (threshold - c) / m
        
        try:
            # Simple linear regression using polyfit
            m, c = np.polyfit(x.flatten(), y, 1)
            
            # If slope is <= 0, the usage is stable or decreasing
            if m <= 0:
                return None
                
            # Time to threshold in seconds
            seconds_to_threshold = (threshold - c) / m
            
            # Check if threshold is already passed or in the past
            if seconds_to_threshold <= x[-1][0]:
                return "Already Critical"
                
            prediction_time = start_time + timedelta(seconds=seconds_to_threshold)
            return prediction_time
            
        except Exception as e:
            logger.error(f"Forecasting error: {e}")
            return None

    @staticmethod
    def analyze_trend(values):
        """
        Return the trend direction: 'increasing', 'decreasing', or 'stable'.
        """
        if len(values) < 10:
            return 'analyzing'
            
        # Compare first and second half averages
        mid = len(values) // 2
        first_half = np.mean(values[:mid])
        second_half = np.mean(values[mid:])
        
        diff_pct = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0
        
        if diff_pct > 5:
            return 'increasing'
        elif diff_pct < -5:
            return 'decreasing'
        else:
            return 'stable'

    @staticmethod
    def get_server_forecast(server_id):
        """
        Get forecast report for a specific server.
        OPTIMIZED: Uses composite index (server_id, timestamp) for fast queries.
        Target: < 300ms (vs previous 2485ms)
        """
        from web.models import Metric
        from web.models import db
        from sqlalchemy import func, desc
        import time

        start_time = time.time()
        now = datetime.utcnow()
        latest_ts = db.session.query(
            func.max(Metric.timestamp)
        ).filter(Metric.server_id == server_id).scalar()

        cache_entry = HealthForecaster._cache.get(server_id)
        if cache_entry:
            age_sec = (now - cache_entry['cached_at']).total_seconds()
            if (
                age_sec <= HealthForecaster._cache_ttl_sec
                and cache_entry.get('latest_ts') == latest_ts
            ):
                cached_query_ms = (time.time() - start_time) * 1000
                if cached_query_ms > 100:
                    logger.warning(f"Forecast cache lookup took {cached_query_ms:.1f}ms")
                return cache_entry['result']
        
        # OPTIMIZED: Use composite index (server_id, timestamp) for instant filtering
        # Fetch latest 600 points in ONE efficient query using the index
        yesterday = now - timedelta(hours=24)
        
        metrics = db.session.query(
            Metric.timestamp,
            Metric.cpu_util_percent,
            Metric.ram_util_percent
        ).filter(
            Metric.server_id == server_id,
            Metric.timestamp >= yesterday
        ).order_by(desc(Metric.timestamp)).limit(600).all()
        
        # Log query performance
        query_ms = (time.time() - start_time) * 1000
        if query_ms > 500:
            logger.warning(f"Forecast query for server {server_id} took {query_ms:.1f}ms (target: <300ms)")
        else:
            logger.debug(f"Forecast query took {query_ms:.1f}ms")
        
        # Reverse to get chronological order for the ML algorithm
        metrics.reverse()
        
        if not metrics or len(metrics) < 10:
            result = {
                'success': False,
                'message': 'Insufficient historical data for accurate forecasting'
            }
            HealthForecaster._cache[server_id] = {
                'cached_at': now,
                'latest_ts': latest_ts,
                'result': result
            }
            return result

        # Subsample if still too dense for fast regression
        if len(metrics) > 200:
            step = max(1, len(metrics) // 200)
            metrics = metrics[::step]
            
        timestamps = [m.timestamp for m in metrics]
        cpu_values = [m.cpu_util_percent or 0 for m in metrics]
        ram_values = [m.ram_util_percent or 0 for m in metrics]
        
        cpu_prediction = HealthForecaster.predict_threshold_arrival(timestamps, cpu_values)
        ram_prediction = HealthForecaster.predict_threshold_arrival(timestamps, ram_values)
        
        cpu_trend = HealthForecaster.analyze_trend(cpu_values)
        ram_trend = HealthForecaster.analyze_trend(ram_values)
        
        # Recommendation logic
        recommendation = "System health is stable. No proactive actions required."
        if cpu_trend == 'increasing' or ram_trend == 'increasing':
            recommendation = "Resource usage is trending upwards. RECOMMENDATION: Check for memory leaks, rogue processes, or plan for resource expansion if usage persists."
        
        if isinstance(cpu_prediction, datetime):
            recommendation = f"CRITICAL: CPU usage predicted to hit 95% threshold at approx {cpu_prediction.strftime('%H:%M')} UTC. Proactive maintenance recommended."
        elif isinstance(ram_prediction, datetime):
            recommendation = f"CRITICAL: RAM usage predicted to hit 95% threshold at approx {ram_prediction.strftime('%H:%M')} UTC. Proactive maintenance recommended."

        result = {
            'success': True,
            'cpu': {
                'trend': cpu_trend,
                'prediction': cpu_prediction.isoformat() + ('Z' if isinstance(cpu_prediction, datetime) and cpu_prediction.tzinfo is None else '') if isinstance(cpu_prediction, datetime) else str(cpu_prediction)
            },
            'ram': {
                'trend': ram_trend,
                'prediction': ram_prediction.isoformat() + ('Z' if isinstance(ram_prediction, datetime) and ram_prediction.tzinfo is None else '') if isinstance(ram_prediction, datetime) else str(ram_prediction)
            },
            'recommendation': recommendation,
            'query_time_ms': query_ms
        }

        HealthForecaster._cache[server_id] = {
            'cached_at': now,
            'latest_ts': latest_ts,
            'result': result
        }
        return result
        metrics = db.session.query(
            Metric.timestamp,
            Metric.cpu_util_percent,
            Metric.ram_util_percent
        ).filter(
            Metric.server_id == server_id,
            Metric.timestamp >= yesterday
        ).order_by(Metric.timestamp.desc()).limit(600).all()
        
        # Reverse to get chronological order for the ML algorithm
        metrics.reverse()
        
        if not metrics or len(metrics) < 10:
            result = {
                'success': False,
                'message': 'Insufficient historical data for accurate forecasting'
            }
            HealthForecaster._cache[server_id] = {
                'cached_at': now,
                'latest_ts': latest_ts,
                'result': result
            }
            return result

        # Subsample if still too dense for fast regression
        if len(metrics) > 200:
            step = max(1, len(metrics) // 200)
            metrics = metrics[::step]
            
        timestamps = [m.timestamp for m in metrics]
        cpu_values = [m.cpu_util_percent or 0 for m in metrics]
        ram_values = [m.ram_util_percent or 0 for m in metrics]
        
        cpu_prediction = HealthForecaster.predict_threshold_arrival(timestamps, cpu_values)
        ram_prediction = HealthForecaster.predict_threshold_arrival(timestamps, ram_values)
        
        cpu_trend = HealthForecaster.analyze_trend(cpu_values)
        ram_trend = HealthForecaster.analyze_trend(ram_values)
        
        # Recommendation logic
        recommendation = "System health is stable. No proactive actions required."
        if cpu_trend == 'increasing' or ram_trend == 'increasing':
            recommendation = "Resource usage is trending upwards. RECOMMENDATION: Check for memory leaks, rogue processes, or plan for resource expansion if usage persists."
        
        if isinstance(cpu_prediction, datetime):
            recommendation = f"CRITICAL: CPU usage predicted to hit 95% threshold at approx {cpu_prediction.strftime('%H:%M')} UTC. Proactive maintenance recommended."
        elif isinstance(ram_prediction, datetime):
            recommendation = f"CRITICAL: RAM usage predicted to hit 95% threshold at approx {ram_prediction.strftime('%H:%M')} UTC. Proactive maintenance recommended."

        result = {
            'success': True,
            'cpu': {
                'trend': cpu_trend,
                'prediction': cpu_prediction.isoformat() + ('Z' if isinstance(cpu_prediction, datetime) and cpu_prediction.tzinfo is None else '') if isinstance(cpu_prediction, datetime) else str(cpu_prediction)
            },
            'ram': {
                'trend': ram_trend,
                'prediction': ram_prediction.isoformat() + ('Z' if isinstance(ram_prediction, datetime) and ram_prediction.tzinfo is None else '') if isinstance(ram_prediction, datetime) else str(ram_prediction)
            },
            'recommendation': recommendation
        }

        HealthForecaster._cache[server_id] = {
            'cached_at': now,
            'latest_ts': latest_ts,
            'result': result
        }
        return result
