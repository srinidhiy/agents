from playwright.async_api import async_playwright, Page, Browser
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from dotenv import load_dotenv
import os
import requests
import json
import asyncio
import nest_asyncio
from langchain.agents import Tool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_experimental.tools import PythonREPLTool
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Optional, List

# Allow nested event loops (needed for running async in sync wrappers within async context)
nest_asyncio.apply()

load_dotenv(override=True)
pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_user = os.getenv("PUSHOVER_USER")
pushover_url = "https://api.pushover.net/1/messages.json"
serper = GoogleSerperAPIWrapper()

# Sandbox directory for screenshots and files
SANDBOX_DIR = "sandbox"
os.makedirs(SANDBOX_DIR, exist_ok=True)


class ShoppingTools:
    """Shopping tools that use a shared browser instance"""
    
    def __init__(self, browser: Browser):
        self.browser = browser
        self.page: Optional[Page] = None
    
    async def _get_page(self) -> Page:
        """Get or create a browser page"""
        if self.page is None or self.page.is_closed():
            context = await self.browser.new_context()
            self.page = await context.new_page()
        return self.page
    
    async def search_products(self, query: str, site: str = "google_shopping", max_results: int = 5) -> str:
        """
        Search for products on a shopping site.
        
        Args:
            query: The product search query
            site: One of 'amazon', 'target', 'google_shopping', or 'all'
            max_results: Maximum number of results to return
        """
        page = await self._get_page()
        results = []
        
        try:
            if site == "amazon" or site == "all":
                await page.goto(f"https://www.amazon.com/s?k={query.replace(' ', '+')}", timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)  # Allow dynamic content to load
                
                # Extract product info from Amazon
                products = await page.query_selector_all('[data-component-type="s-search-result"]')
                for i, product in enumerate(products[:max_results]):
                    try:
                        title_el = await product.query_selector('h2 a span')
                        title = await title_el.inner_text() if title_el else "Unknown"
                        
                        price_el = await product.query_selector('.a-price .a-offscreen')
                        price = await price_el.inner_text() if price_el else "Price not available"
                        
                        link_el = await product.query_selector('h2 a')
                        link = await link_el.get_attribute('href') if link_el else ""
                        if link and not link.startswith('http'):
                            link = f"https://www.amazon.com{link}"
                        
                        rating_el = await product.query_selector('.a-icon-star-small .a-icon-alt')
                        rating = await rating_el.inner_text() if rating_el else "No rating"
                        
                        results.append({
                            "site": "Amazon",
                            "title": title[:100],
                            "price": price,
                            "rating": rating,
                            "url": link
                        })
                    except Exception:
                        continue
            
            if site == "target" or site == "all":
                await page.goto(f"https://www.target.com/s?searchTerm={query.replace(' ', '+')}", timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(3)  # Target needs more time for JS
                
                # Extract product info from Target
                products = await page.query_selector_all('[data-test="product-grid"] > div')
                for i, product in enumerate(products[:max_results]):
                    try:
                        title_el = await product.query_selector('[data-test="product-title"]')
                        title = await title_el.inner_text() if title_el else "Unknown"
                        
                        price_el = await product.query_selector('[data-test="current-price"] span')
                        price = await price_el.inner_text() if price_el else "Price not available"
                        
                        link_el = await product.query_selector('a[href*="/p/"]')
                        link = await link_el.get_attribute('href') if link_el else ""
                        if link and not link.startswith('http'):
                            link = f"https://www.target.com{link}"
                        
                        results.append({
                            "site": "Target",
                            "title": title[:100],
                            "price": price,
                            "rating": "See details",
                            "url": link
                        })
                    except Exception:
                        continue
            
            if site == "google_shopping" or site == "all":
                await page.goto(f"https://www.google.com/search?q={query.replace(' ', '+')}&tbm=shop", timeout=30000)
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)
                
                # Extract from Google Shopping
                products = await page.query_selector_all('.sh-dgr__grid-result')
                for i, product in enumerate(products[:max_results]):
                    try:
                        title_el = await product.query_selector('h3')
                        title = await title_el.inner_text() if title_el else "Unknown"
                        
                        price_el = await product.query_selector('.a8Pemb')
                        price = await price_el.inner_text() if price_el else "Price not available"
                        
                        link_el = await product.query_selector('a')
                        link = await link_el.get_attribute('href') if link_el else ""
                        if link and not link.startswith('http'):
                            link = f"https://www.google.com{link}"
                        
                        results.append({
                            "site": "Google Shopping",
                            "title": title[:100],
                            "price": price,
                            "rating": "See details",
                            "url": link
                        })
                    except Exception:
                        continue
            
            if not results:
                return f"No products found for '{query}' on {site}. Try a different search term or site."
            
            # Format results nicely
            output = f"Found {len(results)} products for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. [{r['site']}] {r['title']}\n"
                output += f"   Price: {r['price']} | Rating: {r['rating']}\n"
                output += f"   URL: {r['url']}\n\n"
            
            return output
            
        except Exception as e:
            return f"Error searching for products: {str(e)}"
    
    async def get_product_details(self, url: str) -> str:
        """
        Get detailed information about a product from its URL.
        
        Args:
            url: The product page URL
        """
        page = await self._get_page()
        
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)
            
            details = {"url": url}
            
            # Detect site and extract accordingly
            if "amazon.com" in url:
                title_el = await page.query_selector('#productTitle')
                details["title"] = await title_el.inner_text() if title_el else "Unknown"
                
                price_el = await page.query_selector('.a-price .a-offscreen')
                details["price"] = await price_el.inner_text() if price_el else "Price not available"
                
                rating_el = await page.query_selector('#acrPopover')
                details["rating"] = await rating_el.get_attribute('title') if rating_el else "No rating"
                
                reviews_el = await page.query_selector('#acrCustomerReviewText')
                details["reviews"] = await reviews_el.inner_text() if reviews_el else "No reviews"
                
                avail_el = await page.query_selector('#availability span')
                details["availability"] = await avail_el.inner_text() if avail_el else "Unknown"
                
                desc_el = await page.query_selector('#feature-bullets')
                details["description"] = await desc_el.inner_text() if desc_el else "No description"
                details["site"] = "Amazon"
                
            elif "target.com" in url:
                title_el = await page.query_selector('[data-test="product-title"]')
                details["title"] = await title_el.inner_text() if title_el else "Unknown"
                
                price_el = await page.query_selector('[data-test="product-price"]')
                details["price"] = await price_el.inner_text() if price_el else "Price not available"
                
                rating_el = await page.query_selector('[data-test="rating-count"]')
                details["rating"] = await rating_el.inner_text() if rating_el else "No rating"
                
                details["reviews"] = "See page for reviews"
                details["availability"] = "Check page for availability"
                
                desc_el = await page.query_selector('[data-test="item-details-description"]')
                details["description"] = await desc_el.inner_text() if desc_el else "No description"
                details["site"] = "Target"
                
            else:
                # Generic extraction
                title_el = await page.query_selector('h1')
                details["title"] = await title_el.inner_text() if title_el else "Unknown"
                details["price"] = "Check page for price"
                details["rating"] = "Check page for rating"
                details["reviews"] = "Check page for reviews"
                details["availability"] = "Check page for availability"
                details["description"] = "Visit the page for details"
                details["site"] = "Other"
            
            # Clean up description
            if "description" in details and details["description"]:
                details["description"] = details["description"][:500] + "..." if len(details["description"]) > 500 else details["description"]
            
            output = f"Product Details from {details['site']}:\n"
            output += f"Title: {details['title']}\n"
            output += f"Price: {details['price']}\n"
            output += f"Rating: {details['rating']}\n"
            output += f"Reviews: {details['reviews']}\n"
            output += f"Availability: {details['availability']}\n"
            output += f"Description: {details['description']}\n"
            output += f"URL: {details['url']}\n"
            
            return output
            
        except Exception as e:
            return f"Error getting product details: {str(e)}"
    
    async def add_to_cart(self, url: str) -> str:
        """
        Navigate to a product and add it to cart.
        
        Args:
            url: The product page URL
        """
        page = await self._get_page()
        
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)
            
            # Take screenshot before attempting
            before_screenshot = f"{SANDBOX_DIR}/before_add_to_cart.png"
            await page.screenshot(path=before_screenshot)
            
            success = False
            message = ""
            
            if "amazon.com" in url:
                # Try to find and click Amazon's Add to Cart button
                add_button = await page.query_selector('#add-to-cart-button')
                if add_button:
                    await add_button.click()
                    await asyncio.sleep(3)
                    success = True
                    message = "Clicked 'Add to Cart' on Amazon"
                else:
                    # Try alternative buttons
                    alt_button = await page.query_selector('[name="submit.add-to-cart"]')
                    if alt_button:
                        await alt_button.click()
                        await asyncio.sleep(3)
                        success = True
                        message = "Clicked 'Add to Cart' on Amazon (alternative button)"
                    else:
                        message = "Could not find Add to Cart button on Amazon. You may need to log in first."
                        
            elif "target.com" in url:
                # Try to find and click Target's Add to Cart button
                add_button = await page.query_selector('[data-test="shippingButton"]')
                if add_button:
                    await add_button.click()
                    await asyncio.sleep(3)
                    success = True
                    message = "Clicked 'Add to Cart' on Target"
                else:
                    # Try alternative
                    alt_button = await page.query_selector('button[data-test*="addToCart"]')
                    if alt_button:
                        await alt_button.click()
                        await asyncio.sleep(3)
                        success = True
                        message = "Clicked 'Add to Cart' on Target (alternative button)"
                    else:
                        message = "Could not find Add to Cart button on Target. You may need to log in or select options first."
            else:
                # Generic: try common button selectors
                selectors = [
                    'button:has-text("Add to Cart")',
                    'button:has-text("Add to Bag")',
                    '[class*="add-to-cart"]',
                    '[id*="add-to-cart"]',
                ]
                for selector in selectors:
                    try:
                        button = await page.query_selector(selector)
                        if button:
                            await button.click()
                            await asyncio.sleep(3)
                            success = True
                            message = f"Clicked add to cart button"
                            break
                    except:
                        continue
                if not success:
                    message = "Could not find Add to Cart button. Please add manually."
            
            # Take screenshot after
            after_screenshot = f"{SANDBOX_DIR}/after_add_to_cart.png"
            await page.screenshot(path=after_screenshot)
            
            if success:
                return f"SUCCESS: {message}\nScreenshot saved to: {after_screenshot}\nPlease check the browser to verify the item was added and complete checkout."
            else:
                return f"UNABLE TO ADD: {message}\nScreenshot saved to: {after_screenshot}\nPlease add the item manually in the browser."
                
        except Exception as e:
            return f"Error adding to cart: {str(e)}"
    
    async def take_screenshot(self, filename: str = "screenshot.png") -> str:
        """
        Take a screenshot of the current browser page.
        
        Args:
            filename: Name for the screenshot file (saved to sandbox directory)
        """
        page = await self._get_page()
        
        try:
            if not filename.endswith('.png'):
                filename += '.png'
            
            filepath = f"{SANDBOX_DIR}/{filename}"
            await page.screenshot(path=filepath, full_page=False)
            
            return f"Screenshot saved to: {filepath}"
            
        except Exception as e:
            return f"Error taking screenshot: {str(e)}"
    
    async def compare_products(self, urls: str) -> str:
        """
        Compare multiple products side by side.
        
        Args:
            urls: Comma-separated list of product URLs to compare
        """
        url_list = [u.strip() for u in urls.split(',')]
        
        if len(url_list) < 2:
            return "Please provide at least 2 URLs separated by commas to compare products."
        
        if len(url_list) > 5:
            url_list = url_list[:5]
        
        products = []
        
        for url in url_list:
            details = await self.get_product_details(url)
            products.append({"url": url, "details": details})
        
        output = "=== Product Comparison ===\n\n"
        for i, p in enumerate(products, 1):
            output += f"--- Product {i} ---\n"
            output += p["details"]
            output += "\n"
        
        output += "\n=== Summary ===\n"
        output += f"Compared {len(products)} products. Review the details above to make your decision."
        
        return output
    
    def get_tools(self) -> List[Tool]:
        """Get all shopping tools as LangChain tools"""
        
        # Create wrapper functions for async methods
        def search_products_wrapper(query: str, site: str = "google_shopping", max_results: int = 5) -> str:
            return asyncio.get_event_loop().run_until_complete(
                self.search_products(query, site, max_results)
            )
        
        def get_product_details_wrapper(url: str) -> str:
            return asyncio.get_event_loop().run_until_complete(
                self.get_product_details(url)
            )
        
        def add_to_cart_wrapper(url: str) -> str:
            return asyncio.get_event_loop().run_until_complete(
                self.add_to_cart(url)
            )
        
        def take_screenshot_wrapper(filename: str = "screenshot.png") -> str:
            return asyncio.get_event_loop().run_until_complete(
                self.take_screenshot(filename)
            )
        
        def compare_products_wrapper(urls: str) -> str:
            return asyncio.get_event_loop().run_until_complete(
                self.compare_products(urls)
            )
        
        return [
            Tool(
                name="search_products",
                func=search_products_wrapper,
                description="""Search for products on shopping sites. 
                Arguments: query (required), site (optional: 'amazon', 'target', 'google_shopping', or 'all'), max_results (optional, default 5).
                Example: search_products('wireless headphones', 'amazon', 5)"""
            ),
            Tool(
                name="get_product_details",
                func=get_product_details_wrapper,
                description="""Get detailed information about a specific product from its URL.
                Arguments: url (required) - the full product page URL.
                Returns: title, price, rating, reviews, availability, and description."""
            ),
            Tool(
                name="add_to_cart",
                func=add_to_cart_wrapper,
                description="""Add a product to the shopping cart. Navigate to the product URL and click the Add to Cart button.
                Arguments: url (required) - the full product page URL.
                Note: User should be logged into the shopping site for this to work."""
            ),
            Tool(
                name="take_screenshot",
                func=take_screenshot_wrapper,
                description="""Take a screenshot of the current browser page.
                Arguments: filename (optional) - name for the screenshot file.
                The screenshot is saved to the sandbox directory."""
            ),
            Tool(
                name="compare_products",
                func=compare_products_wrapper,
                description="""Compare multiple products side by side.
                Arguments: urls (required) - comma-separated list of product URLs to compare.
                Example: compare_products('https://amazon.com/product1, https://target.com/product2')"""
            ),
        ]


async def playwright_tools():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=browser)
    return toolkit.get_tools(), browser, playwright


def push(text: str):
    """Send a push notification to the user"""
    requests.post(pushover_url, data = {"token": pushover_token, "user": pushover_user, "message": text})
    return "success"


def get_file_tools():
    toolkit = FileManagementToolkit(root_dir="sandbox")
    return toolkit.get_tools()


async def other_tools(browser: Browser = None):
    push_tool = Tool(name="send_push_notification", func=push, description="Use this tool when you want to send a push notification")
    file_tools = get_file_tools()

    tool_search = Tool(
        name="search",
        func=serper.run,
        description="Use this tool when you want to get the results of an online web search"
    )

    wikipedia = WikipediaAPIWrapper()
    wiki_tool = WikipediaQueryRun(api_wrapper=wikipedia)

    python_repl = PythonREPLTool()
    
    # Add shopping tools if browser is provided
    shopping_tools = []
    if browser:
        shopping = ShoppingTools(browser)
        shopping_tools = shopping.get_tools()
    
    return file_tools + [push_tool, tool_search, python_repl, wiki_tool] + shopping_tools

