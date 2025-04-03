var config = {
    mode: "fixed_servers",
    rules: {
      singleProxy: {
        scheme: "http",
        host: "xyz.com",
        port: parseInt("12345")
      },
      bypassList: ["localhost"]
    }
  };
  
  chrome.proxy.settings.set({ value: config, scope: "regular" }, function() {});
  
  chrome.webRequest.onAuthRequired.addListener(
    function(details) {
      return {
        authCredentials: {
          username: "abc12345",
          password: "0987654321"
        }
      };
    },
    { urls: ["<all_urls>"] },
    ['blocking']
  );
  