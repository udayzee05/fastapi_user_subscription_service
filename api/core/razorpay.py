import razorpay
from config import settings

def get_razorpay_client(test_mode=settings.RAZORPAY_TEST_MODE):
    """
    Returns the appropriate Razorpay client based on the mode.
    
    :param test_mode: If True, returns the test Razorpay client. Defaults to False.
    :return: An instance of Razorpay client.
    """
    if test_mode:
        return razorpay.Client(auth=(settings.TEST_RAZORPAY_API_KEY, settings.TEST_RAZORPAY_SECRET_KEY))
    else:
        return razorpay.Client(auth=(settings.RAZORPAY_API_KEY, settings.RAZORPAY_SECRET_KEY))


client = get_razorpay_client()