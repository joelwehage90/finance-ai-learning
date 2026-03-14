const path = require("path");
const webpack = require("webpack");
const HtmlWebpackPlugin = require("html-webpack-plugin");

module.exports = {
  entry: {
    taskpane: "./src/taskpane/index.tsx",
    dialog: "./src/auth/dialog.ts",
    callback: "./src/auth/callback.ts",
  },
  output: {
    path: path.resolve(__dirname, "dist"),
    filename: "[name].js",
    clean: true,
  },
  resolve: {
    extensions: [".ts", ".tsx", ".js"],
  },
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
      {
        test: /\.css$/,
        use: ["style-loader", "css-loader"],
      },
    ],
  },
  plugins: [
    new webpack.DefinePlugin({
      "process.env.API_BASE_URL": JSON.stringify(process.env.API_BASE_URL || ""),
    }),
    new HtmlWebpackPlugin({
      template: "./src/taskpane/taskpane.html",
      filename: "taskpane.html",
      chunks: ["taskpane"],
    }),
    new HtmlWebpackPlugin({
      template: "./src/auth/dialog.html",
      filename: "dialog.html",
      chunks: ["dialog"],
    }),
    new HtmlWebpackPlugin({
      template: "./src/auth/callback.html",
      filename: "callback.html",
      chunks: ["callback"],
    }),
  ],
  devServer: {
    static: path.resolve(__dirname, "dist"),
    port: 3000,
    hot: true,
    headers: {
      "Access-Control-Allow-Origin": "*",
    },
  },
};
